import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS 
from google.cloud import speech 
from google.cloud import storage 
import ffmpeg 
import uuid 
from dotenv import load_dotenv 
import json 
import datetime # Zaman işlemleri için

load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed' 
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
os.makedirs(PROCESSED_FOLDER, exist_ok=True) 

GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'SENIN_GCS_KOVA_ADIN_BURAYA_GELMELI') 

speech_client = speech.SpeechClient() 
storage_client = storage.Client() 

@app.route('/')
def hello_world():
    """Basit bir test noktası."""
    return 'Merhaba Dunya! Arka Uç Uygulamasi Çalışıyor!'

def format_srt_time(seconds):
    milliseconds = int(seconds * 1000)
    ms = milliseconds % 1000
    seconds = int(milliseconds / 1000) % 60
    minutes = int(milliseconds / (1000 * 60)) % 60
    hours = int(milliseconds / (1000 * 60 * 60))

    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

def create_srt_file(subtitles_data, file_path):
    """
    Verilen altyazı verilerinden bir SRT dosyası oluşturur.
    subtitles_data: [{speaker, text, startTime, endTime}]
    file_path: Oluşturulacak SRT dosyasının tam yolu
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(subtitles_data):
        

            start_time_str = format_srt_time(sub['startTime'])
            end_time_str = format_srt_time(sub['endTime'])

            f.write(f"{i + 1}\n")
            f.write(f"{start_time_str} --> {end_time_str}\n")

            color_map = {
                'Konuşmacı 1': '#FF0000', 
                'Konuşmacı 2': '#0000FF', 
                'Konuşmacı 3': '#00FF00', 
                'Bilinmeyen Konuşmacı': '#808080' 
            }
            speaker_color = color_map.get(sub['speaker'], '#FFFFFF')
            
            f.write(f'<font color="{speaker_color}">{sub["speaker"]}:</font> {sub["text"]}\n\n')
    app.logger.info(f"SRT dosyası oluşturuldu: {file_path}")

@app.route('/process-video', methods=['POST'])
def process_video():
    """Video dosyasını alır, işler ve altyazıları döndürür."""
    if 'video' not in request.files:
        return jsonify({'error': 'Video dosyası bulunamadı'}), 400

    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({'error': 'Dosya adı boş'}), 400

    if video_file:
        file_id = str(uuid.uuid4())
        original_video_filename = video_file.filename
        
        # Dosya uzantısını koru
        file_extension = os.path.splitext(original_video_filename)[1] 
        video_local_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_original{file_extension}")
        audio_local_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.wav")
        srt_local_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.srt")
        processed_video_local_path = os.path.join(PROCESSED_FOLDER, f"processed_{file_id}{file_extension}")
        
        gcs_audio_uri = None 
        gcs_processed_video_url = None

        try:
            video_file.save(video_local_path)
            app.logger.info(f"Orijinal video yerel olarak kaydedildi: {video_local_path}")

            ffmpeg.input(video_local_path).output(audio_local_path, ac=1, ar=16000).run(overwrite_output=True)
            app.logger.info(f"Ses çıkarıldı ve WAV'a dönüştürüldü: {audio_local_path}")

            # 2. Ses dosyasını Google Cloud Storage'a yükle
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob_name_audio = f"audio/{file_id}.wav"
            blob_audio = bucket.blob(blob_name_audio)
            blob_audio.upload_from_filename(audio_local_path)
            gcs_audio_uri = f"gs://{GCS_BUCKET_NAME}/{blob_name_audio}"
            app.logger.info(f"Ses dosyası GCS'ye yüklendi: {gcs_audio_uri}")

            audio_for_recognition = speech.RecognitionAudio(uri=gcs_audio_uri)
            diarization_config = speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=1,
                max_speaker_count=10,
            )
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code='tr-TR', 
                enable_automatic_punctuation=True,
                diarization_config=diarization_config
            )
            app.logger.info("Google Speech-to-Text API'ye GCS URI ile istek gönderiliyor...")
            operation = speech_client.long_running_recognize(config=config, audio=audio_for_recognition)
            response = operation.result(timeout=600) 
            app.logger.info(f"Google Speech-to-Text Ham Yanıt: {response}")

            subtitles_raw = []
            if response.results:
                for result in response.results:
                    if result.alternatives: 
                        for word_info in result.alternatives[0].words:
                            speaker_tag = f"Konuşmacı {word_info.speaker_tag}" if word_info.speaker_tag else "Bilinmeyen Konuşmacı"
                            word_start_time = word_info.start_time.total_seconds()
                            word_end_time = word_info.end_time.total_seconds()
                            subtitles_raw.append({
                                'speaker': speaker_tag,
                                'text': word_info.word,
                                'startTime': word_start_time,
                                'endTime': word_end_time
                            })
                app.logger.info(f"API'den {len(subtitles_raw)} kelime bilgisi alındı.")
            else:
                app.logger.warning("Google Speech-to-Text API'den kelime bazlı sonuç alınamadı.")

            final_subtitles = []
            if subtitles_raw:
                current_speaker = None
                current_text = []
                segment_start_time = 0.0
                segment_end_time = 0.0

                for i, word_data in enumerate(subtitles_raw):
                    word_speaker = word_data['speaker']
                    word_text = word_data['text']
                    word_start = word_data['startTime']
                    word_end = word_data['endTime']

                    if current_speaker is None or current_speaker != word_speaker or \
                       (word_start - segment_end_time) > 1.5: 
                        
                        if current_text: 
                            final_subtitles.append({
                                'id': str(uuid.uuid4()),
                                'speaker': current_speaker,
                                'text': ' '.join(current_text),
                                'startTime': segment_start_time,
                                'endTime': segment_end_time
                            })
                        
                        current_speaker = word_speaker
                        current_text = [word_text]
                        segment_start_time = word_start
                        segment_end_time = word_end
                    else: 
                        current_text.append(word_text)
                        segment_end_time = word_end 
                    
                    if i == len(subtitles_raw) - 1 and current_text:
                        final_subtitles.append({
                            'id': str(uuid.uuid4()),
                            'speaker': current_speaker,
                            'text': ' '.join(current_text),
                            'startTime': segment_start_time,
                            'endTime': segment_end_time
                        })
                app.logger.info(f"Final Speech-to-Text altyazı blokları oluşturuldu: {len(final_subtitles)}")
            else:
                app.logger.warning("Altyazı oluşturulamadı: final_subtitles boş.")

            if final_subtitles:
                create_srt_file(final_subtitles, srt_local_path)
                app.logger.info(f"SRT dosyası oluşturuldu: {srt_local_path}")
            else:
                app.logger.warning("Final altyazı verisi olmadığı için SRT dosyası oluşturulamadı.")
            if final_subtitles: 
                app.logger.info(f"Altyazılar videoya gömülüyor: {processed_video_local_path}")
                try:
                    ffmpeg.input(video_local_path).output(
                        processed_video_local_path,
                        vf=f"subtitles='{os.path.normpath(srt_local_path).replace(os.sep, '/')}'", 
                        acodec='copy', 
                        vcodec='libx264', 
                        crf=23, 
                        preset='medium'
                    ).run(overwrite_output=True)
                    app.logger.info("Altyazılı video başarıyla oluşturuldu.")

                    blob_name_processed_video = f"processed_videos/{file_id}{file_extension}"
                    blob_processed_video = bucket.blob(blob_name_processed_video)
                    blob_processed_video.upload_from_filename(processed_video_local_path)
                    gcs_processed_video_url = blob_processed_video.public_url 
                    app.logger.info(f"İşlenmiş video GCS'ye yüklendi: {gcs_processed_video_url}")
                except ffmpeg.Error as e:
                    app.logger.error(f"FFmpeg altyazı gömme hatası: {e.stderr.decode('utf-8')}")
                    return jsonify({'error': f"Altyazılar videoya gömülürken FFmpeg hatası oluştu: {e.stderr.decode('utf-8')}"}), 500
            else:
                app.logger.warning("Altyazı verisi olmadığı için videoya gömme işlemi atlandı.")


            return jsonify({
                'subtitles': final_subtitles,
                'processedVideoUrl': gcs_processed_video_url 
            }), 200

        except ffmpeg.Error as e:
            app.logger.error(f"FFmpeg hatası: {e.stderr.decode('utf-8')}", exc_info=True)
            return jsonify({'error': f"Video veya ses işlenirken bir FFmpeg hatası oluştu: {e.stderr.decode('utf-8')}"}), 500
        except Exception as e:
            app.logger.error(f"Beklenmedik bir hata oluştu: {e}", exc_info=True)
            return jsonify({'error': f"Beklenmedik bir hata oluştu: {str(e)}. Lütfen sunucu loglarını kontrol edin."}), 500
        finally:
            
            if os.path.exists(video_local_path):
                os.remove(video_local_path)
                app.logger.info(f"Orijinal video dosyası temizlendi: {video_local_path}")
            if os.path.exists(audio_local_path):
                os.remove(audio_local_path)
                app.logger.info(f"Ses dosyası temizlendi: {audio_local_path}")
            if os.path.exists(srt_local_path):
                os.remove(srt_local_path)
                app.logger.info(f"SRT dosyası temizlendi: {srt_local_path}")
            if os.path.exists(processed_video_local_path):
                os.remove(processed_video_local_path)
                app.logger.info(f"İşlenmiş video yerel dosyası temizlendi: {processed_video_local_path}")
            
            if gcs_audio_uri:
                try:
                    bucket_name = gcs_audio_uri.split('/')[2]
                    blob_path = '/'.join(gcs_audio_uri.split('/')[3:])
                    bucket = storage_client.bucket(bucket_name)
                    blob = bucket.blob(blob_path)
                    if blob.exists():
                        blob.delete()
                        app.logger.info(f"GCS ses dosyası temizlendi: {gcs_audio_uri}")
                except Exception as gcs_e:
                    app.logger.warning(f"GCS ses dosyasını temizlerken hata oluştu: {gcs_e}")


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)


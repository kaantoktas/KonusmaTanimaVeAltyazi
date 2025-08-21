import React, { useState } from "react";

const App = () => {
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [processingMessage, setProcessingMessage] = useState("");
  const [processedSubtitles, setProcessedSubtitles] = useState([]);
  const [speakerColors, setSpeakerColors] = useState({});

  const availableColors = [
    "text-blue-600",
    "text-green-600",
    "text-purple-600",
    "text-red-600",
    "text-yellow-600",
    "text-indigo-600",
    "text-pink-600",
    "text-teal-600",
  ];

  const getSpeakerColor = (speakerId) => {
    if (!speakerColors[speakerId]) {
      const newColorIndex =
        Object.keys(speakerColors).length % availableColors.length;
      setSpeakerColors((prevColors) => ({
        ...prevColors,
        [speakerId]: availableColors[newColorIndex],
      }));
      return availableColors[newColorIndex];
    }
    return speakerColors[speakerId];
  };

  const handleVideoChange = (event) => {
    const file = event.target.files[0];
    if (file && file.type.startsWith("video/")) {
      setSelectedVideo(file);
      setProcessingMessage("");
      setProcessedSubtitles([]);
      setSpeakerColors({});
    } else {
      setSelectedVideo(null);
      setProcessingMessage(
        "Lütfen geçerli bir video dosyası (.mp4, .mov, vb.) seçin."
      );
    }
  };

  const handleProcessVideo = async () => {
    if (!selectedVideo) {
      setProcessingMessage("Lütfen önce bir video dosyası seçin.");
      return;
    }

    setUploading(true);
    setProcessingMessage(
      "Video yükleniyor ve işleniyor... Bu işlem video boyutuna ve konuşma süresine göre zaman alabilir."
    );
    setProcessedSubtitles([]);

    const formData = new FormData();
    formData.append("video", selectedVideo);

    try {
      const response = await fetch("http://127.0.0.1:5000/process-video", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Video işlenirken bir hata oluştu.");
      }

      const data = await response.json();

      if (data.subtitles && data.subtitles.length > 0) {
        const subtitlesWithColors = data.subtitles.map((sub, index) => ({
          ...sub,
          color: getSpeakerColor(sub.speaker),
        }));
        setProcessedSubtitles(subtitlesWithColors);
        setProcessingMessage(
          "Video başarıyla işlendi ve altyazılar oluşturuldu!"
        );
      } else {
        setProcessingMessage(
          "Video işlendi ancak altyazı bulunamadı veya konuşma algılanamadı."
        );
      }
    } catch (error) {
      console.error("Video işlenirken hata oluştu:", error);
      setProcessingMessage(
        `Video işlenirken bir hata oluştu: ${error.message}. Lütfen konsolu kontrol edin.`
      );
      setProcessedSubtitles([]);
    } finally {
      setUploading(false);
    }
  };
  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-100 to-purple-100 p-4 sm:p-8 flex items-center justify-center font-inter antialiased">
      <script src="https://cdn.tailwindcss.com"></script>
      <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
        rel="stylesheet"
      />

      <style
        dangerouslySetInnerHTML={{
          __html: `
                body { font-family: 'Inter', sans-serif; }
                .rounded-xl { border-radius: 0.75rem; }
            `,
        }}
      />

      <div className="bg-white p-6 sm:p-8 rounded-xl shadow-2xl w-full max-w-4xl transform transition-all duration-300 hover:shadow-3xl">
        <h1 className="text-3xl sm:text-4xl font-bold text-center text-gray-800 mb-6 sm:mb-8">
          Video Konuşma Tanıma & Altyazı Oluşturucu
        </h1>
        <p className="text-center text-gray-600 mb-6 max-w-2xl mx-auto text-sm sm:text-base">
          Videoyu yükleyerek içindeki konuşmaları tanıyıp, kişilere özel renkli
          altyazılar oluşturun.
        </p>

        <div className="mb-6 sm:mb-8 p-4 border border-gray-300 rounded-lg bg-gray-50">
          <label
            htmlFor="videoUpload"
            className="block text-gray-700 text-lg font-semibold mb-3"
          >
            Video Yükle
          </label>
          <input
            type="file"
            id="videoUpload"
            accept="video/*"
            onChange={handleVideoChange}
            className="w-full text-gray-800 file:mr-4 file:py-2 file:px-4
                                   file:rounded-lg file:border-0 file:text-sm file:font-semibold
                                   file:bg-purple-50 file:text-purple-700
                                   hover:file:bg-purple-100 cursor-pointer transition-all duration-200"
          />
          {selectedVideo && (
            <p className="mt-3 text-sm text-gray-600">
              Seçilen video:{" "}
              <span className="font-medium text-purple-700">
                {selectedVideo.name}
              </span>
            </p>
          )}
        </div>

        <div className="flex justify-center mb-6 sm:mb-8">
          <button
            onClick={handleProcessVideo}
            disabled={!selectedVideo || uploading}
            className={`w-full max-w-xs bg-purple-600 text-white font-bold py-3 px-6 rounded-lg shadow-lg
                                    ${
                                      !selectedVideo || uploading
                                        ? "opacity-50 cursor-not-allowed"
                                        : "hover:bg-purple-700 transition-transform transform hover:scale-105"
                                    }
                                    focus:outline-none focus:ring-2 focus:ring-purple-400 focus:ring-opacity-75`}
          >
            {uploading ? "İşleniyor..." : "Videoyu İşle"}
          </button>
        </div>

        {processingMessage && (
          <p className="text-center text-purple-700 font-medium mb-6 sm:mb-8 p-3 bg-purple-50 rounded-lg">
            {processingMessage}
          </p>
        )}

        <h2 className="text-2xl font-bold text-gray-800 mb-4 border-b-2 border-purple-300 pb-2">
          Oluşturulan Altyazılar
        </h2>
        <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 min-h-[150px] max-h-[400px] overflow-y-auto">
          {processedSubtitles.length > 0 ? (
            processedSubtitles.map((subtitle) => (
              <p
                key={subtitle.id}
                className={`mb-2 ${subtitle.color} font-medium text-sm sm:text-base`}
              >
                <span className="font-semibold">{subtitle.speaker}:</span>{" "}
                {subtitle.text}
                <span className="text-gray-500 text-xs ml-2">
                  [{subtitle.startTime.toFixed(1)}s -{" "}
                  {subtitle.endTime.toFixed(1)}s]
                </span>
              </p>
            ))
          ) : (
            <p className="text-gray-500 italic text-center py-10 text-sm sm:text-base">
              Video işlendikten sonra altyazılar burada görünecektir.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default App;

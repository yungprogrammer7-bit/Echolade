
const textInput = document.getElementById("textInput");
const voiceSelect = document.getElementById("voiceSelect");

const speakBtn = document.getElementById("speakBtn");
const pauseBtn = document.getElementById("pauseBtn");
const resumeBtn = document.getElementById("resumeBtn");
const stopBtn = document.getElementById("stopBtn");
const clearBtn = document.getElementById("clearBtn");

const charCount = document.getElementById("charCount");
const status = document.getElementById("status");

const rate = document.getElementById("rate");
const pitch = document.getElementById("pitch");
const volume = document.getElementById("volume");

let voices = [];

function loadVoices() {
  voices = speechSynthesis.getVoices();

  const previousVoice = voiceSelect.value;
  voiceSelect.innerHTML = "";

  voices.forEach((voice, index) => {
    const option = document.createElement("option");

    option.value = index;
    option.textContent =
      `${voice.name} (${voice.lang})`;

    voiceSelect.appendChild(option);
  });

  if (previousVoice && voices[previousVoice]) {
    voiceSelect.value = previousVoice;
  }
}

loadVoices();

speechSynthesis.onvoiceschanged = loadVoices;

// Character counter
textInput.addEventListener("input", () => {
  charCount.textContent =
    `${textInput.value.length} characters`;
});

// Speech speed
rate.addEventListener("input", () => {
  document.getElementById("rateValue").textContent =
    `${rate.value}x`;
});

// Pitch
pitch.addEventListener("input", () => {
  document.getElementById("pitchValue").textContent =
    pitch.value;
});

// Volume
volume.addEventListener("input", () => {
  document.getElementById("volumeValue").textContent =
    `${Math.round(volume.value * 100)}%`;
});

// Speak
speakBtn.addEventListener("click", () => {
  const text = textInput.value.trim();

  if (!text) {
    status.textContent = "Please enter some text first.";
    return;
  }

  if (!("speechSynthesis" in window)) {
    status.textContent = "Speech synthesis is not supported.";
    return;
  }

  speechSynthesis.cancel();

  const speech = new SpeechSynthesisUtterance(text);

  const selectedVoice = voices[voiceSelect.value];

  if (selectedVoice) {
    speech.voice = selectedVoice;
  }

  speech.rate = Number(rate.value);
  speech.pitch = Number(pitch.value);
  speech.volume = Number(volume.value);

  speech.onstart = () => {
    status.textContent = "Speaking...";
  };

  speech.onend = () => {
    status.textContent = "Speech completed.";
  };

  speech.onerror = (event) => {
    status.textContent = `Speech error: ${event.error}`;
  };

  speechSynthesis.speak(speech);
});

// Pause
pauseBtn.addEventListener("click", () => {
  if (speechSynthesis.speaking) {
    speechSynthesis.pause();
    status.textContent = "Speech paused.";
  }
});

// Resume
resumeBtn.addEventListener("click", () => {
  if (speechSynthesis.paused) {
    speechSynthesis.resume();
    status.textContent = "Speech resumed.";
  }
});

// Stop
stopBtn.addEventListener("click", () => {
  speechSynthesis.cancel();
  status.textContent = "Speech stopped.";
});

// Clear text
clearBtn.addEventListener("click", () => {
  speechSynthesis.cancel();
  textInput.value = "";
  charCount.textContent = "0 characters";
  status.textContent = "Text cleared.";
});

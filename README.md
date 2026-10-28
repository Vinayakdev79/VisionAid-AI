# VisionAid AI 👁️🤖

**An AI-powered assistive vision system designed to help visually impaired people understand their surroundings through real-time camera analysis and spoken descriptions.**

VisionAid AI uses a camera and a locally running vision-language model to describe scenes and communicate meaningful changes through speech. The current prototype runs on a Windows laptop using Python and Ollama.

## ✨ Features

- **Live Camera Preview:** View the camera feed directly in the application.
- **AI Scene Understanding:** Analyze camera images and generate natural-language scene descriptions.
- **Automatic Scene Monitoring:** Monitor the camera feed and analyze meaningful visual changes.
- **Speech Output:** Speak scene descriptions using Windows Speech API (SAPI) through `pywin32`.
- **Local AI Inference:** Use Ollama with the `qwen3.5:4b` model.
- **Privacy-Focused Processing:** Camera images are analyzed using the local Ollama service rather than requiring a cloud vision API.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application |
| OpenCV | Camera access and image processing |
| Ollama | Local AI model runtime |
| Qwen 3.5 4B | Image understanding and scene descriptions |
| CustomTkinter | Desktop application interface |
| pywin32 / Windows SAPI | Speech output |
| Pillow | Image handling |
| NumPy | Image processing operations |
| Requests | Communication with the local Ollama API |

## ⚙️ Prerequisites

Before running VisionAid AI, install:

1. **Python** — a version compatible with the dependencies.
2. **Ollama** — [Download Ollama](https://ollama.com/download).
3. A working camera and speakers or headphones.
4. Windows, for the current SAPI-based speech implementation.

## 🚀 Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Vinayakdev79/VisionAid-AI.git
cd VisionAid-AI
```

### 2. Create a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Download the AI model

Install and start Ollama, then run:

```powershell
ollama pull qwen3.5:4b
```

Verify that the model is available:

```powershell
ollama list
```

Ensure the Ollama service is running locally.

### 5. Run VisionAid AI

```powershell
python main.py
```

The application should open the camera preview, analyze the scene, and speak the resulting description.

## 🧠 How It Works

1. The application captures frames from the camera.
2. OpenCV processes the frames and supports visual-change detection.
3. When analysis is required, the application sends an image to the locally running Ollama model.
4. Qwen generates a description of the scene or a meaningful visual change.
5. Windows SAPI converts the generated text into speech.

## 📁 Project Structure

```text
VisionAid-AI/
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

## 🔒 Privacy and Safety

VisionAid AI is an experimental assistive-technology prototype. Its current local inference design helps reduce the need to transmit camera images to third-party vision APIs.

- Keep the camera pointed only where appropriate.
- Do not upload private images, credentials, or personal data.
- AI-generated descriptions may be inaccurate or incomplete.
- Do not rely on the prototype as the sole means of detecting hazards or navigating unfamiliar environments.

## 🗺️ Future Improvements

- Improved obstacle and hazard detection.
- More accurate real-time scene-change detection.
- Support for additional languages and speech options.
- Better performance and accessibility controls.
- Testing with visually impaired users to evaluate usability and reliability.

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request describing your improvements.

## 📄 License

This project is intended to be open source. Add a `LICENSE` file to the repository with your chosen license terms before distributing it under an open-source license.

## 👨‍💻 Author

**Vinayak Katiyar**

GitHub: [@Vinayakdev79](https://github.com/Vinayakdev79)

---

*VisionAid AI — Making the visual world more accessible through artificial intelligence.*

# ai-crime-detection-camera

This project is an AI-powered smart surveillance system that detects weapons and emergencies in real time using live camera feeds. It uses YOLOv8 for fast, on-device inference and supports multiple low-cost cameras such as smartphones, USB webcams, or Raspberry Pi cameras.

When a weapon is detected, the system generates an instant alert with camera location and a snapshot. A reviewer can validate the alert through a simple web dashboard.
If confirmed, the system extracts the last 30 seconds of video from an in-memory ring buffer, encrypts it using AES/Fernet, and saves it as secure evidence. If rejected, no footage is stored.

This architecture ensures real-time safety while maintaining strict privacy, making it suitable for campuses, apartments, offices, malls, and public spaces.

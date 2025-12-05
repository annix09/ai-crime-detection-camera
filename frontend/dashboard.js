// dashboard.js - simple fetch to /api/alerts and populate cards
async function loadAlerts() {
  try {
    const res = await fetch("/api/alerts");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const alerts = await res.json();

    const container = document.getElementById("alerts-container");
    if (!container) return; // not on this page
    container.innerHTML = "";

    alerts.forEach(alert => {
      const card = document.createElement("div");
      card.className = "bg-white p-4 rounded shadow hover:shadow-lg transition";

      card.innerHTML = `
        <img src="${alert.snapshot}" alt="snapshot" class="w-full h-40 object-cover rounded mb-2">
        <p class="font-semibold">${alert.location || alert.camera_location || "Unknown"}</p>
        <p class="text-sm text-gray-600">Confidence: ${alert.confidence ?? alert.confidence_score ?? "N/A"}%</p>
        <a href="/alert/${alert.id}" class="mt-2 inline-block px-3 py-1 bg-blue-600 text-white rounded">Review</a>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load alerts:", err);
    const container = document.getElementById("alerts-container");
    if (container) container.innerHTML = '<p class="text-red-600">Unable to load alerts</p>';
  }
}

if (document.readyState !== "loading") {
  loadAlerts();
} else {
  document.addEventListener("DOMContentLoaded", loadAlerts);
}
setInterval(loadAlerts, 2000);

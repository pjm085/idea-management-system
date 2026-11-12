// ===== DASHBOARD GREETING AND CLOCK =====

function updateGreeting() {
  const now = new Date();
  const hour = now.getHours();

  let greeting;

  if (hour < 12) {
    greeting = "GOOD MORNING,";
  } else if (hour < 17) {
    greeting = "GOOD AFTERNOON,";
  } else {
    greeting = "GOOD EVENING,";
  }

  const greetingElement = document.getElementById("greeting-word");
  const dateElement = document.getElementById("current-date");

  if (greetingElement) {
    greetingElement.textContent = greeting;
  }

  if (dateElement) {
    const date = now.toLocaleDateString(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });

    const time = now.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    dateElement.textContent = `${date} · ${time}`;
  }
}

function initializeDashboard() {
  updateGreeting();

  setInterval(updateGreeting, 1000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeDashboard, {
    once: true,
  });
} else {
  initializeDashboard();
}

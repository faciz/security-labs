"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  let toastTimer;

  function icons() {
    if (window.lucide) window.lucide.createIcons();
  }

  function icon(name) {
    const element = document.createElement("i");
    element.dataset.lucide = name;
    element.setAttribute("aria-hidden", "true");
    return element;
  }

  function toast(message) {
    clearTimeout(toastTimer);
    byId("toast").textContent = message;
    byId("toast").hidden = false;
    toastTimer = setTimeout(() => {
      byId("toast").hidden = true;
    }, 4500);
  }

  function message(id, text, error = false) {
    const element = byId(id);
    element.textContent = text;
    element.hidden = !text;
    element.classList.toggle("error", error);
  }

  async function request(path, { method = "GET", body, timeout = 15000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {
        method,
        headers:
          body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        cache: "no-store",
      });
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error(
          `The server returned an unexpected response (${response.status}).`,
        );
      }
      if (!response.ok) {
        throw new Error(
          data.error ||
            data.result?.error ||
            data.record?.error ||
            `Request failed (${response.status}).`,
        );
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError")
        throw new Error(
          "Request timed out. The server may still be processing it; check activity before retrying.",
        );
      if (error instanceof TypeError)
        throw new Error(
          "Cannot reach VaultBank. Check that the local server is running.",
        );
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function readStorage(key) {
    try {
      return JSON.parse(localStorage.getItem(key));
    } catch {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  }

  const initials = (name) =>
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0] || "")
      .join("")
      .toUpperCase();
  const money = (amount) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount);
  const time = (value) =>
    new Date(value).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = byId(button.dataset.close);
      if (dialog.getAttribute("aria-busy") !== "true") dialog.close();
    });
  });
  document.querySelectorAll("dialog").forEach((dialog) => {
    dialog.addEventListener("cancel", (event) => {
      if (dialog.getAttribute("aria-busy") === "true") event.preventDefault();
    });
  });
  byId("brief-open").addEventListener("click", () =>
    byId("brief-dialog").showModal(),
  );
  window.VaultUI = {
    byId,
    icons,
    icon,
    toast,
    message,
    request,
    readStorage,
    writeStorage,
    initials,
    money,
    time,
  };
  icons();
})();

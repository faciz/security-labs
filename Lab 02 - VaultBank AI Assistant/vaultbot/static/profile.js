"use strict";

(() => {
  const { byId, icon, icons, request, message, initials, toast } =
    window.VaultUI;
  const name = byId("display-name");
  const about = byId("profile-about");
  const save = byId("save-profile");
  const discard = byId("discard-profile");
  let saved = null;
  let busy = false;

  function dirty() {
    return (
      saved &&
      (name.value !== saved.display_name || about.value !== saved.about)
    );
  }

  function update() {
    byId("profile-length").textContent =
      `${about.value.length.toLocaleString()} / 4,000`;
    byId("profile-name-preview").textContent =
      name.value.trim() || "Guest User";
    byId("profile-initials").textContent = initials(name.value || "Guest User");
    byId("profile-state").textContent = busy
      ? "Saving"
      : dirty()
        ? "Unsaved changes"
        : "Up to date";
    save.disabled = busy || !saved || !dirty() || !name.value.trim();
    discard.disabled = busy || !dirty();
  }

  function restore() {
    name.value = saved.display_name;
    about.value = saved.about;
    update();
  }

  async function loadProfile() {
    discard.disabled = true;
    byId("profile-state").textContent = "Loading";
    try {
      const data = await request("/api/profile");
      saved = data.profile;
      name.disabled = false;
      about.disabled = false;
      discard.replaceChildren(
        icon("undo-2"),
        document.createTextNode("Discard changes"),
      );
      restore();
      message("profile-result", "");
      icons();
    } catch (error) {
      byId("profile-state").textContent = "Unavailable";
      message("profile-result", error.message, true);
      discard.replaceChildren(
        icon("refresh-cw"),
        document.createTextNode("Retry loading"),
      );
      discard.disabled = false;
      icons();
    }
  }

  name.addEventListener("input", update);
  about.addEventListener("input", update);
  discard.addEventListener("click", () => {
    if (saved) {
      restore();
      message("profile-result", "");
    } else void loadProfile();
  });
  byId("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !saved || !dirty()) return;
    busy = true;
    name.disabled = true;
    about.disabled = true;
    update();
    message("profile-result", "");
    try {
      const data = await request("/api/profile", {
        method: "POST",
        body: { display_name: name.value, about: about.value },
      });
      saved = data.profile;
      restore();
      message("profile-result", "Profile saved.");
      toast("Profile saved.");
    } catch (error) {
      message("profile-result", error.message, true);
    } finally {
      busy = false;
      name.disabled = false;
      about.disabled = false;
      update();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  void loadProfile();
})();

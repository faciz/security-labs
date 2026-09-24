"use strict";

(() => {
  const {
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
  } = window.VaultUI;
  const storageKey = "vaultbank.workspace.v2";
  const account = document.body.dataset.account;
  const modelConfigured = document.body.dataset.modelConfigured === "true";
  const input = byId("chat-input");
  const saved = readStorage(storageKey);
  let local = {
    runId: null,
    messages: [],
    history: [],
    notes: "",
    hints: {},
    selected: "secret_leaked",
    draft: "",
  };
  let lab = null;
  let busy = false;
  let transferPending = false;
  let ownPin = "";
  let pinVisible = false;
  let events;

  function persist() {
    local.notes = byId("field-notes").value;
    local.draft = input.value;
    return writeStorage(storageKey, local);
  }

  function selectMission(key) {
    if (!byId(`mission-${key}`)) return;
    local.selected = key;
    document.querySelectorAll("[data-mission]").forEach((button) => {
      const selected = button.dataset.mission === key;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
      byId(button.getAttribute("aria-controls")).hidden = !selected;
    });
  }

  function renderHints() {
    document.querySelectorAll("[data-hint]").forEach((button) => {
      const key = button.dataset.hint;
      const count = Math.min(Math.max(Number(local.hints[key]) || 0, 0), 3);
      const list = byId(`hints-${key}`);
      list.hidden = !count;
      Array.from(list.children).forEach((item, index) => {
        item.hidden = index >= count;
      });
      button.querySelector(".hint-count").textContent = `${count} / 3`;
      button.querySelector("span").textContent =
        count === 3
          ? "All hints revealed"
          : count
            ? "Reveal next hint"
            : "Reveal a hint";
      button.disabled = count === 3;
    });
  }

  function updateComposer() {
    byId("send-message").disabled =
      busy || !modelConfigured || !lab || !input.value.trim();
    byId("message-length").textContent =
      `${input.value.length.toLocaleString()} / 8,000`;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }

  function renderMessage(entry) {
    const wrapper = document.createElement("article");
    wrapper.className = `message ${entry.role}`;
    const heading = document.createElement("div");
    heading.className = "message-heading";
    heading.append(
      icon(entry.role === "assistant" ? "sparkles" : "user-round"),
    );
    const author = document.createElement("strong");
    author.textContent = entry.role === "assistant" ? "VaultBot" : "You";
    const stamp = document.createElement("span");
    stamp.textContent = time(entry.at);
    heading.append(author, stamp);
    const content = document.createElement("div");
    content.className = "message-text";
    content.textContent = entry.content;
    wrapper.append(heading, content);
    if (entry.trace?.length) {
      const details = document.createElement("details");
      details.className = "tool-trace";
      const summary = document.createElement("summary");
      summary.append(
        icon("wrench"),
        document.createTextNode(
          `${entry.trace.length} tool call${entry.trace.length === 1 ? "" : "s"}`,
        ),
      );
      const list = document.createElement("ol");
      entry.trace.forEach((call) => {
        const item = document.createElement("li");
        item.textContent = `${call.tool}: ${call.status}`;
        list.append(item);
      });
      details.append(summary, list);
      wrapper.append(details);
    }
    if (entry.role === "assistant") {
      const actions = document.createElement("div");
      actions.className = "message-actions";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "icon-button";
      copy.title = "Copy reply";
      copy.setAttribute("aria-label", "Copy reply");
      copy.append(icon("copy"));
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(entry.content);
          toast("Reply copied.");
        } catch {
          toast("Clipboard access is unavailable in this browser.");
        }
      });
      actions.append(copy);
      wrapper.append(actions);
    }
    byId("messages").append(wrapper);
    byId("welcome").hidden = true;
    icons();
    return wrapper;
  }

  function restoreConversation() {
    byId("messages").replaceChildren();
    byId("welcome").hidden = local.messages.length > 0;
    local.messages.forEach(renderMessage);
    input.value = local.draft;
    byId("field-notes").value = local.notes;
    renderHints();
    selectMission(local.selected);
    updateComposer();
    byId("chat-scroll").scrollTop = byId("chat-scroll").scrollHeight;
  }

  function initializeRun(snapshot) {
    const candidate = lab ? null : saved;
    local = {
      runId: snapshot.run_id,
      messages: [],
      history: [],
      notes: "",
      hints: {},
      selected: "secret_leaked",
      draft: "",
    };
    if (candidate?.runId === snapshot.run_id) {
      local.messages = Array.isArray(candidate.messages)
        ? candidate.messages
            .filter(
              (entry) =>
                ["user", "assistant"].includes(entry.role) &&
                typeof entry.content === "string",
            )
            .slice(-60)
        : [];
      local.history = Array.isArray(candidate.history)
        ? candidate.history
            .filter(
              (entry) =>
                ["user", "assistant"].includes(entry.role) &&
                typeof entry.content === "string",
            )
            .slice(-20)
        : [];
      local.notes =
        typeof candidate.notes === "string"
          ? candidate.notes.slice(0, 6000)
          : "";
      local.draft =
        typeof candidate.draft === "string"
          ? candidate.draft.slice(0, 8000)
          : "";
      local.hints =
        candidate.hints && typeof candidate.hints === "object"
          ? candidate.hints
          : {};
      local.selected =
        typeof candidate.selected === "string"
          ? candidate.selected
          : "secret_leaked";
    }
    if (lab) {
      byId("transfer-form").reset();
      byId("code-form").reset();
      byId("transfer-dialog").close();
      byId("service-result").hidden = false;
      byId("service-result").textContent = "Service reachable";
      byId("service-status-dot").classList.remove("amber");
      ["chat-error", "pin-error", "transfer-result", "code-result"].forEach(
        (id) => message(id, ""),
      );
      pinVisible = false;
      updatePin();
    }
    restoreConversation();
    persist();
  }

  function renderEvents(snapshot) {
    const fragment = document.createDocumentFragment();
    snapshot.events
      .slice()
      .reverse()
      .forEach((entry) => {
        const item = document.createElement("li");
        const marker = document.createElement("span");
        marker.className = `event-icon ${entry.kind}`;
        marker.append(
          icon(
            entry.kind === "capture"
              ? "flag"
              : entry.kind === "error"
                ? "circle-alert"
                : entry.kind === "blocked"
                  ? "shield-alert"
                  : "activity",
          ),
        );
        const body = document.createElement("div");
        body.className = "event-body";
        const title = document.createElement("p");
        title.textContent = entry.title;
        const meta = document.createElement("span");
        meta.textContent = `${time(entry.at)} / ${entry.source}`;
        body.append(title, meta);
        item.append(marker, body);
        fragment.append(item);
      });
    byId("activity-list").replaceChildren(fragment);
    byId("activity-empty").hidden = snapshot.events.length > 0;
    byId("event-count").textContent = String(snapshot.events.length);
  }

  function applyLab(snapshot) {
    if (!snapshot?.run_id || !Array.isArray(snapshot.missions)) return;
    if (lab && new Date(snapshot.started_at) < new Date(lab.started_at)) return;
    if (lab?.run_id === snapshot.run_id && snapshot.sequence < lab.sequence)
      return;
    const previous = lab;
    const changedRun = local.runId !== snapshot.run_id;
    if (changedRun) initializeRun(snapshot);
    lab = snapshot;
    const core = snapshot.missions.filter((mission) => !mission.bonus);
    const completed = core.filter(
      (mission) => snapshot.captured[mission.key],
    ).length;
    byId("core-count").textContent = `${completed} of ${core.length}`;
    byId("mission-progress").max = core.length;
    byId("mission-progress").value = completed;
    byId("score").textContent = snapshot.score;
    byId("run-id").textContent = snapshot.run_id;
    byId("activity-run").textContent = `Run ${snapshot.run_id}`;
    byId("run-metrics").textContent =
      `${snapshot.turns} turns / ${snapshot.tool_calls} tools`;
    byId("completion-banner").hidden = !snapshot.core_complete;
    snapshot.missions.forEach((mission) => {
      const button = document.querySelector(`[data-mission="${mission.key}"]`);
      const completed = Boolean(snapshot.captured[mission.key]);
      const locked = Boolean(
        mission.prerequisite && !snapshot.captured[mission.prerequisite],
      );
      const status = completed
        ? "completed"
        : locked
          ? "locked"
          : "not completed";
      button.classList.toggle("completed", completed);
      button.setAttribute(
        "aria-label",
        `${mission.number}: ${mission.title}, ${status}, ${mission.points} points`,
      );
      const number = button.querySelector(".mission-number");
      number.replaceChildren(
        completed
          ? icon("check")
          : locked
            ? icon("lock")
            : document.createTextNode(mission.number),
      );
      const prerequisite = byId(`mission-${mission.key}`).querySelector(
        ".mission-prerequisite",
      );
      if (prerequisite) prerequisite.hidden = !locked;
      byId(`mission-${mission.key}`).querySelector(".mission-debrief").hidden =
        !completed;
      if (
        previous &&
        !changedRun &&
        completed &&
        !previous.captured[mission.key]
      )
        toast(`Mission complete: ${mission.title}.`);
    });
    if (!previous || changedRun || previous.sequence !== snapshot.sequence)
      renderEvents(snapshot);
    if (previous && (changedRun || previous.sequence !== snapshot.sequence))
      void loadAccount();
    updateComposer();
    icons();
  }

  function connection(online, text) {
    const label = byId("connection-label");
    label.querySelector(".status-dot").classList.toggle("amber", !online);
    label.querySelector("span:last-child").textContent = text;
  }

  async function refreshLab() {
    try {
      applyLab(await request("/api/lab"));
    } catch (error) {
      connection(false, "Offline");
      toast(error.message);
    }
  }

  function connectEvents() {
    if (!window.EventSource || events) return;
    events = new EventSource("/api/events");
    events.onopen = () => connection(true, "Live");
    events.onmessage = (event) => {
      try {
        applyLab(JSON.parse(event.data));
        connection(true, "Live");
      } catch {
        connection(false, "Sync delayed");
      }
    };
    events.onerror = () => connection(false, "Reconnecting");
  }

  function updatePin() {
    byId("account-pin").textContent = pinVisible
      ? ownPin || "Unavailable"
      : "******";
    const button = byId("toggle-account-pin");
    const label = pinVisible ? "Hide training PIN" : "Show training PIN";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", String(pinVisible));
    button.replaceChildren(icon(pinVisible ? "eye-off" : "eye"));
    icons();
  }

  async function loadAccount() {
    const button = byId("refresh-account");
    button.disabled = true;
    try {
      const [data, profile] = await Promise.all([
        request("/api/account", {
          method: "POST",
          body: { account_id: account },
        }),
        request("/api/profile"),
      ]);
      byId("account-balance").textContent = money(data.record.balance);
      byId("account-tier").textContent = data.record.tier || "Guest";
      byId("account-email").textContent = data.record.email || "Not provided";
      byId("customer-name").textContent = profile.profile.display_name;
      byId("customer-initials").textContent = initials(
        profile.profile.display_name,
      );
      ownPin = String(data.record.transfer_pin || "");
      updatePin();
      message("account-error", "");
    } catch (error) {
      message("account-error", error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function setBusy(value) {
    busy = value;
    byId("typing").hidden = !value;
    byId("new-conversation").disabled = value;
    byId("reset-open").disabled = value;
    document.querySelectorAll("[data-starter]").forEach((button) => {
      button.disabled = value || !modelConfigured;
    });
    byId("chat-form").setAttribute("aria-busy", String(value));
    updateComposer();
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || busy || !modelConfigured || !lab) return;
    const requestRun = lab.run_id;
    const history = local.history.slice(-20).map((entry) => ({
      role: entry.role,
      content: entry.content.slice(0, 8000),
    }));
    while (
      history.reduce(
        (length, entry) => length + entry.content.length,
        text.length,
      ) > 32000
    )
      history.splice(0, 2);
    const user = { role: "user", content: text, at: new Date().toISOString() };
    const pending = renderMessage(user);
    input.value = "";
    message("chat-error", "");
    setBusy(true);
    byId("chat-scroll").scrollTop = byId("chat-scroll").scrollHeight;
    try {
      const data = await request("/api/chat", {
        method: "POST",
        body: { history: [...history, { role: "user", content: text }] },
        timeout: 145000,
      });
      if (lab.run_id !== requestRun) return;
      if (typeof data.reply !== "string" || !data.reply)
        throw new Error("The model returned no reply.");
      const reply = {
        role: "assistant",
        content: data.reply,
        at: new Date().toISOString(),
        trace: data.trace || [],
      };
      local.messages.push(user, reply);
      local.messages = local.messages.slice(-60);
      local.history = [
        ...history,
        { role: "user", content: text },
        { role: "assistant", content: data.reply },
      ].slice(-20);
      renderMessage(reply);
      persist();
      await refreshLab();
      byId("chat-scroll").scrollTop = byId("chat-scroll").scrollHeight;
    } catch (error) {
      pending.remove();
      if (lab.run_id === requestRun) {
        input.value = text;
        message("chat-error", error.message, true);
        byId("welcome").hidden = local.messages.length > 0;
        persist();
      }
    } finally {
      setBusy(false);
      input.focus({ preventScroll: true });
    }
  }

  document.querySelectorAll("[data-mission]").forEach((button) =>
    button.addEventListener("click", () => {
      selectMission(button.dataset.mission);
      persist();
    }),
  );
  document.querySelectorAll("[data-hint]").forEach((button) =>
    button.addEventListener("click", () => {
      local.hints[button.dataset.hint] = Math.min(
        (Number(local.hints[button.dataset.hint]) || 0) + 1,
        3,
      );
      renderHints();
      persist();
    }),
  );
  byId("field-notes").addEventListener("input", () => {
    byId("notes-status").textContent = persist()
      ? "Saved in this browser"
      : "Browser storage unavailable; notes are not saved";
  });
  input.addEventListener("input", () => {
    updateComposer();
    persist();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void sendMessage();
    }
  });
  byId("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void sendMessage();
  });
  document.querySelectorAll("[data-starter]").forEach((button) =>
    button.addEventListener("click", () => {
      input.value = button.dataset.starter;
      void sendMessage();
    }),
  );
  byId("new-conversation").addEventListener("click", () => {
    if (busy) return;
    local.history = [];
    local.messages = [];
    local.draft = "";
    restoreConversation();
    message("chat-error", "");
    persist();
    toast("New conversation. Lab progress is unchanged.");
    input.focus({ preventScroll: true });
  });

  const tabs = [byId("chat-tab"), byId("activity-tab")];
  function selectTab(selected) {
    tabs.forEach((tab) => {
      const active = tab === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      byId(tab.getAttribute("aria-controls")).hidden = !active;
    });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      const target =
        event.key === "Home"
          ? tabs[0]
          : event.key === "End"
            ? tabs[1]
            : tabs[1 - index];
      selectTab(target);
      target.focus();
    });
  });

  byId("refresh-account").addEventListener("click", loadAccount);
  byId("toggle-account-pin").addEventListener("click", () => {
    pinVisible = !pinVisible;
    updatePin();
  });
  byId("check-service").addEventListener("click", async () => {
    const button = byId("check-service");
    const result = byId("service-result");
    const indicator = byId("service-status-dot");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    result.hidden = false;
    result.textContent = "Checking...";
    indicator.classList.add("amber");
    try {
      const diagnostics = await request("/api/diagnostics");
      const reachable =
        diagnostics.service === "VaultBot" && diagnostics.status === "ok";
      result.textContent = reachable
        ? "Service reachable"
        : "Service unavailable";
      indicator.classList.toggle("amber", !reachable);
    } catch {
      result.textContent = "Service unavailable";
    } finally {
      button.removeAttribute("aria-busy");
      button.disabled = false;
    }
  });

  byId("transfer-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (transferPending) return;
    const recipient = byId("transfer-to").value.trim();
    if (recipient === account) {
      message("transfer-result", "Choose a different recipient account.", true);
      return;
    }
    message("transfer-result", "");
    message("pin-error", "");
    byId("transfer-pin").value = "";
    byId("confirm-recipient").textContent = recipient;
    byId("confirm-amount").textContent = money(
      Number(byId("transfer-amount").value),
    );
    byId("transfer-dialog").showModal();
    byId("transfer-pin").focus();
  });
  byId("authorize-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (transferPending) return;
    transferPending = true;
    byId("authorize-transfer").disabled = true;
    byId("transfer-dialog").setAttribute("aria-busy", "true");
    message("pin-error", "");
    try {
      const data = await request("/api/transfer", {
        method: "POST",
        body: {
          from_account: account,
          to_account: byId("transfer-to").value.trim(),
          amount: byId("transfer-amount").value,
          authorization: byId("transfer-pin").value.trim(),
        },
      });
      byId("transfer-dialog").close();
      byId("transfer-pin").value = "";
      message(
        "transfer-result",
        `${money(data.result.amount)} transferred to ${data.result.to}.`,
      );
      await loadAccount();
      await refreshLab();
    } catch (error) {
      message("pin-error", error.message, true);
    } finally {
      transferPending = false;
      byId("authorize-transfer").disabled = false;
      byId("transfer-dialog").setAttribute("aria-busy", "false");
    }
  });
  byId("transfer-dialog").addEventListener("close", () => {
    byId("transfer-pin").value = "";
  });

  byId("code-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = byId("code-form").querySelector("button");
    if (button.disabled) return;
    button.disabled = true;
    try {
      const data = await request("/api/submit", {
        method: "POST",
        body: { code: byId("vault-code").value.trim() },
      });
      message(
        "code-result",
        data.correct
          ? "Evidence verified. Bonus captured."
          : "That code does not match this lab instance.",
        !data.correct,
      );
      if (data.correct) byId("vault-code").value = "";
      applyLab(data.lab);
    } catch (error) {
      message("code-result", error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  byId("reset-open").addEventListener("click", () => {
    message("reset-error", "");
    byId("reset-dialog").showModal();
  });
  byId("reset-confirm").addEventListener("click", async () => {
    const button = byId("reset-confirm");
    if (button.disabled) return;
    button.disabled = true;
    byId("reset-dialog").setAttribute("aria-busy", "true");
    try {
      const data = await request("/api/reset", {
        method: "POST",
        timeout: 145000,
      });
      applyLab(data.lab);
      byId("reset-dialog").close();
      await loadAccount();
      toast("Lab reset. A fresh investigation is ready.");
    } catch (error) {
      message("reset-error", error.message, true);
    } finally {
      button.disabled = false;
      byId("reset-dialog").setAttribute("aria-busy", "false");
    }
  });

  byId("export-run").addEventListener("click", async () => {
    const button = byId("export-run");
    button.disabled = true;
    try {
      const snapshot = await request("/api/lab");
      applyLab(snapshot);
      const report = {
        schema_version: 1,
        lab: "VaultBank / Lab 02",
        exported_at: new Date().toISOString(),
        run_id: snapshot.run_id,
        started_at: snapshot.started_at,
        score: snapshot.score,
        core_complete: snapshot.core_complete,
        captured: snapshot.captured,
        metrics: {
          turns: snapshot.turns,
          tool_calls: snapshot.tool_calls,
          blocked: snapshot.blocked,
        },
        evidence: snapshot.events,
        missions: snapshot.missions.map((mission) => ({
          title: mission.title,
          completed: snapshot.captured[mission.key],
          mitigation: mission.defense,
        })),
        hints_revealed: local.hints,
        notes: byId("field-notes").value,
      };
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(report, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `vaultbank-investigation-${snapshot.run_id}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Investigation exported. Chat transcripts and PINs are excluded.");
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  window.addEventListener("pagehide", () => {
    events?.close();
    events = null;
  });
  window.addEventListener("pageshow", () => {
    void refreshLab();
    connectEvents();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refreshLab();
  });
  void refreshLab().then(connectEvents);
  void loadAccount();
})();

// ===== SHARED FEATURE INTERACTIONS =====

(() => {
  "use strict";

  function openDialog(id) {
    const dialog = document.getElementById(id);
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "open");
    }
    const input = dialog.querySelector(
      "input:not([type=hidden]), textarea, select",
    );
    if (input) window.setTimeout(() => input.focus(), 50);
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (dialog.classList.contains("dashboard-note-dialog")) {
      dialog.querySelector("form")?.reset();
    }
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-dialog-open]");
    if (openButton) {
      const menu = openButton.closest("details.card-menu");
      if (menu) menu.open = false;
      openDialog(openButton.getAttribute("data-dialog-open"));
      return;
    }

    const closeButton = event.target.closest("[data-dialog-close]");
    if (closeButton) {
      closeDialog(closeButton.closest("dialog"));
      return;
    }

    if (
      event.target instanceof HTMLDialogElement &&
      event.target.classList.contains("feature-dialog")
    ) {
      const rect = event.target.getBoundingClientRect();
      const inside =
        rect.top <= event.clientY &&
        event.clientY <= rect.bottom &&
        rect.left <= event.clientX &&
        event.clientX <= rect.right;
      if (!inside) closeDialog(event.target);
    }
  });

  document.addEventListener("click", (event) => {
    const refreshButton = event.target.closest("[data-refresh-page]");
    if (refreshButton) window.location.reload();
  });

  document.addEventListener("change", (event) => {
    const select = event.target.closest("select[data-submit-on-change]");
    if (select && select.form) select.form.requestSubmit();
  });

  let pendingConfirmForm = null;
  const confirmDialog = document.getElementById("app-confirm-dialog");
  const confirmTitle = document.getElementById("app-confirm-title");
  const confirmMessage = document.getElementById("app-confirm-message");
  const confirmAccept = document.getElementById("app-confirm-accept");

  function closeConfirmDialog() {
    if (!confirmDialog) return;
    if (typeof confirmDialog.close === "function") confirmDialog.close();
    else confirmDialog.removeAttribute("open");
    pendingConfirmForm = null;
  }

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-confirm]");
    if (!form) return;

    if (form.dataset.confirmedSubmit === "true") {
      delete form.dataset.confirmedSubmit;
      return;
    }

    event.preventDefault();
    pendingConfirmForm = form;

    if (confirmTitle) {
      confirmTitle.textContent = form.dataset.confirmTitle || "Are you sure?";
    }
    if (confirmMessage) {
      confirmMessage.textContent =
        form.dataset.confirm || "Continue with this action?";
    }
    if (confirmAccept) {
      confirmAccept.textContent = form.dataset.confirmAction || "Continue";
    }

    if (confirmDialog && typeof confirmDialog.showModal === "function") {
      confirmDialog.showModal();
    } else if (confirmDialog) {
      confirmDialog.setAttribute("open", "open");
    } else {
      pendingConfirmForm = null;
    }
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-confirm-cancel]")) {
      closeConfirmDialog();
      return;
    }
    if (event.target.closest("#app-confirm-accept")) {
      const form = pendingConfirmForm;
      if (!form) return;
      closeConfirmDialog();
      form.dataset.confirmedSubmit = "true";
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }
  });

  if (confirmDialog) {
    confirmDialog.addEventListener("click", (event) => {
      if (event.target !== confirmDialog) return;
      const rect = confirmDialog.getBoundingClientRect();
      const inside =
        rect.top <= event.clientY &&
        event.clientY <= rect.bottom &&
        rect.left <= event.clientX &&
        event.clientX <= rect.right;
      if (!inside) closeConfirmDialog();
    });
    confirmDialog.addEventListener("cancel", () => {
      pendingConfirmForm = null;
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const openDialog = document.querySelector("dialog[open]");
    if (!openDialog) return;
    event.preventDefault();
    if (openDialog === confirmDialog) {
      closeConfirmDialog();
    } else {
      closeDialog(openDialog);
    }
  });

  const noteCreateForm = document.querySelector("form[data-ajax-note-create]");
  if (noteCreateForm) {
    const noteInput = noteCreateForm.querySelector('textarea[name="content"]');
    const submitButton = noteCreateForm.querySelector('button[type="submit"]');
    const feedback = document.querySelector("[data-note-feedback]");

    const element = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };

    function showNoteFeedback(message, isError = false) {
      if (!feedback) return;
      feedback.textContent = message;
      feedback.hidden = false;
      feedback.classList.toggle("is-error", isError);
    }

    function makeNoteCard(note) {
      const card = element("article", "dashboard-sticky-note");
      const allowedNoteColors = new Set([
        "note-color-yellow",
        "note-color-sage",
        "note-color-lavender",
        "note-color-peach",
        "note-color-blue",
      ]);
      const safeColorClass = allowedNoteColors.has(note.color_class)
        ? note.color_class
        : "note-color-sage";
      card.classList.add(safeColorClass);

      const content = element(
        "p",
        "dashboard-sticky-note-content",
        note.content,
      );
      card.appendChild(content);

      const footer = element("div", "dashboard-sticky-note-footer");
      const time = element(
        "time",
        "dashboard-sticky-note-date",
        note.date_label || "",
      );
      time.dateTime = String(note.created_at || "").replace(" ", "T");
      footer.appendChild(time);

      const actions = element("div", "dashboard-sticky-note-actions");
      const editButton = element(
        "button",
        "dashboard-sticky-note-edit-trigger",
      );
      editButton.type = "button";
      editButton.dataset.dialogOpen = `note-edit-dialog-${note.id}`;
      editButton.setAttribute("aria-label", "Edit reminder note");
      editButton.append(
        element("i", "ri-edit-line"),
        element("span", "", "Edit"),
      );
      actions.appendChild(editButton);

      const editDialog = element(
        "dialog",
        "feature-dialog dashboard-note-dialog",
      );
      editDialog.id = `note-edit-dialog-${note.id}`;
      editDialog.setAttribute("aria-labelledby", `note-edit-title-${note.id}`);
      const editForm = element(
        "form",
        "feature-dialog-form dashboard-note-edit-form",
      );
      editForm.method = "POST";
      editForm.action = noteCreateForm.dataset.noteEditUrlTemplate.replace(
        "/0/",
        `/${note.id}/`,
      );
      const csrf = noteCreateForm.querySelector('input[name="csrf_token"]');
      const editCsrf = element("input");
      editCsrf.type = "hidden";
      editCsrf.name = "csrf_token";
      editCsrf.value = csrf ? csrf.value : "";
      editForm.appendChild(editCsrf);

      const editLabel = element("label", "visually-hidden", "Reminder note");
      editLabel.htmlFor = `note-edit-${note.id}`;
      const editTextarea = element("textarea");
      editTextarea.id = `note-edit-${note.id}`;
      editTextarea.name = "content";
      editTextarea.rows = 5;
      editTextarea.maxLength = 1000;
      editTextarea.required = true;
      editTextarea.value = note.content;
      editTextarea.defaultValue = note.content;

      const closeButton = element("button", "dialog-x", "×");
      closeButton.type = "button";
      closeButton.dataset.dialogClose = "";
      closeButton.setAttribute("aria-label", "Close reminder note editor");
      const eyebrow = element("p", "feature-eyebrow", "EDIT REMINDER NOTE");
      const title = element("h2", "", "Edit reminder note");
      title.id = `note-edit-title-${note.id}`;
      const field = element("div", "feature-form-field");
      field.append(editLabel, editTextarea);
      const actionsRow = element("div", "dialog-actions");
      const cancelButton = element(
        "button",
        "feature-button feature-button-secondary",
        "Cancel",
      );
      cancelButton.type = "button";
      cancelButton.dataset.dialogClose = "";
      const saveButton = element("button", "feature-button", "Save changes");
      saveButton.type = "submit";
      actionsRow.append(cancelButton, saveButton);

      editForm.append(editCsrf, closeButton, eyebrow, title, field, actionsRow);
      editDialog.appendChild(editForm);
      card.appendChild(editDialog);

      const deleteForm = element("form");
      deleteForm.method = "POST";
      deleteForm.action = noteCreateForm.dataset.noteDeleteUrlTemplate.replace(
        "/0/",
        `/${note.id}/`,
      );
      deleteForm.dataset.confirm =
        "Are you sure you want to permanently delete this reminder note? This action cannot be undone.";
      deleteForm.dataset.confirmTitle = "Delete reminder note?";
      deleteForm.dataset.confirmAction = "Delete note";
      const deleteCsrf = element("input");
      deleteCsrf.type = "hidden";
      deleteCsrf.name = "csrf_token";
      deleteCsrf.value = csrf ? csrf.value : "";
      deleteForm.appendChild(deleteCsrf);
      const deleteButton = element("button", "dashboard-sticky-note-delete");
      deleteButton.type = "submit";
      deleteButton.setAttribute("aria-label", "Delete reminder note");
      deleteButton.appendChild(element("i", "ri-delete-bin-line"));
      deleteButton.appendChild(element("span", "", "Delete"));
      deleteForm.appendChild(deleteButton);
      actions.appendChild(deleteForm);

      footer.appendChild(actions);
      card.appendChild(footer);
      return card;
    }

    function getOrCreateNoteGrid() {
      const scrollArea = document.querySelector(".dashboard-scroll");
      if (!scrollArea) return null;
      let noteList = scrollArea.querySelector(".dashboard-notes-list");
      if (!noteList) {
        const emptyState = scrollArea.querySelector(".empty-state");
        if (emptyState) emptyState.remove();
        noteList = element("div", "dashboard-notes-list");
        noteList.setAttribute("aria-label", "Saved reminder notes");
        const grid = element("div", "dashboard-notes-grid");
        noteList.appendChild(grid);
        const connections = scrollArea.querySelector(".connections-section");
        scrollArea.insertBefore(noteList, connections || scrollArea.firstChild);
      }
      return noteList.querySelector(".dashboard-notes-grid");
    }

    noteCreateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!noteInput || !noteInput.value.trim()) {
        if (noteInput) noteInput.focus();
        return;
      }
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.classList.add("is-loading");
      }
      try {
        const response = await fetch(noteCreateForm.action, {
          method: "POST",
          body: new FormData(noteCreateForm),
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
          credentials: "same-origin",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.success || !payload.note) {
          throw new Error(
            payload.error ||
              "Your reminder could not be saved. Please try again.",
          );
        }
        const dashboardScroll = document.querySelector(".dashboard-scroll");
        const emptyState = dashboardScroll
          ? dashboardScroll.querySelector(".empty-state")
          : null;
        const emptyStateViewportTop = emptyState
          ? emptyState.getBoundingClientRect().top
          : null;
        const previousDashboardScrollTop = dashboardScroll
          ? dashboardScroll.scrollTop
          : 0;
        const previousWindowScrollY = window.scrollY;
        const grid = getOrCreateNoteGrid();
        if (!grid)
          throw new Error(
            "The reminder area could not be found. Please reload the page.",
          );
        grid.prepend(makeNoteCard(payload.note));
        const noteList = grid.closest(".dashboard-notes-list");
        if (noteList) noteList.scrollTop = 0;

        window.requestAnimationFrame(() => {
          if (dashboardScroll && emptyStateViewportTop !== null && noteList) {
            const currentNoteListTop = noteList.getBoundingClientRect().top;
            dashboardScroll.scrollTop +=
              currentNoteListTop - emptyStateViewportTop;
          } else if (dashboardScroll) {
            dashboardScroll.scrollTop = previousDashboardScrollTop;
          }
          window.scrollTo(0, previousWindowScrollY);
        });
        noteCreateForm.reset();
        showNoteFeedback(payload.message || "Reminder note saved.");
      } catch (error) {
        showNoteFeedback(
          error.message ||
            "Your reminder could not be saved. Please try again.",
          true,
        );
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.classList.remove("is-loading");
        }
      }
    });
  }

  document.addEventListener("click", (event) => {
    document.querySelectorAll("details.card-menu[open]").forEach((menu) => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      document.querySelectorAll("details.card-menu[open]").forEach((menu) => {
        menu.open = false;
      });
    }
  });
})();

// ===== PROFILE FORM INTERACTIONS =====

document.addEventListener("DOMContentLoaded", () => {
  const editToggle = document.getElementById("edit-profile-toggle");
  const editPanel = document.getElementById("profile-edit-panel");
  const cancelEdit = document.getElementById("cancel-profile-edit");
  const profileForm = document.getElementById("profile-details-form");
  const profileName = document.getElementById("profile-name");

  if (editToggle && editPanel && cancelEdit && profileForm) {
    function openEditPanel() {
      editPanel.hidden = false;
      editToggle.setAttribute("aria-expanded", "true");
    }

    function closeEditPanel() {
      profileForm.reset();
      editPanel.hidden = true;
      editToggle.setAttribute("aria-expanded", "false");
    }

    editToggle.addEventListener("click", () => {
      if (editPanel.hidden) {
        openEditPanel();
        profileName?.focus();
      } else {
        closeEditPanel();
      }
    });

    cancelEdit.addEventListener("click", () => {
      closeEditPanel();
      editToggle.focus();
    });

    if (window.location.hash === "#profile-edit-panel") {
      openEditPanel();
    }
  }

  const passwordToggle = document.getElementById("change-password-toggle");
  const passwordPanel = document.getElementById("change-password-panel");

  if (!passwordToggle || !passwordPanel) return;

  function setPasswordExpanded(expanded) {
    passwordToggle.setAttribute("aria-expanded", String(expanded));
    passwordPanel.hidden = !expanded;
  }

  passwordToggle.addEventListener("click", () => {
    setPasswordExpanded(passwordPanel.hidden);
  });

  if (window.location.hash === "#change-password") {
    setPasswordExpanded(true);
    window.requestAnimationFrame(() => {
      passwordPanel.querySelector("[role='alert']")?.focus();
    });
  }
});

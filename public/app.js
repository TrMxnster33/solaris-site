const backdrop = document.querySelector("#auth-backdrop");
const content = document.querySelector("#auth-content");
const toast = document.querySelector("#toast");
let pendingEmail = "";
let toastTimer;
let heartbeatStarted = false;

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3800);
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Bir hata oluştu.");
  return result;
}

function openModal() {
  backdrop.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeModal() {
  backdrop.hidden = true;
  document.body.style.overflow = "";
}

function renderLogin(message = "") {
  content.innerHTML = `
    <h2 id="auth-title">Tekrar hoş geldin.</h2>
    <p class="auth-intro">Solaris'teki yerine dönmek için giriş yap.</p>
    ${message ? `<p class="auth-message">${message}</p>` : ""}
    <form class="auth-form" id="login-form">
      <label class="field">E-posta adresi<input name="email" type="email" autocomplete="email" required></label>
      <label class="field">Parola<input name="password" type="password" autocomplete="current-password" required></label>
      <button class="button button-dark" type="submit">Giriş yap <span>↗</span></button>
    </form>
    <p class="auth-switch">Henüz hesabın yok mu? <button type="button" data-switch="register">Hesap oluştur</button></p>`;
  content.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/login", { email: form.get("email"), password: form.get("password") });
      location.reload();
    } catch (error) {
      renderLogin(error.message);
    }
  });
}

function renderRegister(message = "") {
  content.innerHTML = `
    <h2 id="auth-title">Solaris'e katıl.</h2>
    <p class="auth-intro">Hesabını oluştur; e-posta adresine gelen kodla doğrula.</p>
    ${message ? `<p class="auth-message">${message}</p>` : ""}
    <form class="auth-form" id="register-form">
      <label class="field">Adın<input name="name" autocomplete="name" maxlength="80" required></label>
      <label class="field">E-posta adresi<input name="email" type="email" autocomplete="email" required></label>
      <label class="field">Parola<input name="password" type="password" autocomplete="new-password" minlength="10" required><span>En az 10 karakter</span></label>
      <button class="button button-dark" type="submit">Doğrulama kodu gönder <span>↗</span></button>
    </form>
    <p class="auth-switch">Zaten hesabın var mı? <button type="button" data-switch="login">Giriş yap</button></p>`;
  content.querySelector("#register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    pendingEmail = String(form.get("email")).trim().toLowerCase();
    try {
      const result = await api("/api/register", {
        name: form.get("name"),
        email: pendingEmail,
        password: form.get("password"),
      });
      renderVerify(result.message);
    } catch (error) {
      renderRegister(error.message);
    }
  });
}

function renderVerify(message) {
  content.innerHTML = `
    <h2 id="auth-title">E-postanı kontrol et.</h2>
    <p class="auth-intro">${message} <strong>${pendingEmail}</strong></p>
    <form class="auth-form" id="verify-form">
      <label class="field">6 haneli doğrulama kodu<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required></label>
      <button class="button button-dark" type="submit">E-postayı doğrula <span>↗</span></button>
    </form>
    <p class="auth-switch">Kod gelmedi mi? <button type="button" data-switch="register">Tekrar dene</button></p>`;
  content.querySelector("#verify-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    try {
      const result = await api("/api/verify", { email: pendingEmail, code });
      renderLogin(result.message);
    } catch (error) {
      renderVerify(error.message);
    }
  });
}

document.addEventListener("click", (event) => {
  const authButton = event.target.closest("[data-open-auth]");
  if (authButton) {
    authButton.dataset.openAuth === "login" ? renderLogin() : renderRegister();
    openModal();
  }
  const switchButton = event.target.closest("[data-switch]");
  if (switchButton) {
    switchButton.dataset.switch === "login" ? renderLogin() : renderRegister();
  }
});

document.querySelector(".modal-close").addEventListener("click", closeModal);
backdrop.addEventListener("click", (event) => {
  if (event.target === backdrop) closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !backdrop.hidden) closeModal();
});

const menuButton = document.querySelector(".mobile-menu");
menuButton.addEventListener("click", () => {
  const open = document.querySelector(".topbar").classList.toggle("menu-open");
  menuButton.setAttribute("aria-expanded", String(open));
});

function dashboardElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function cell(row, text) {
  const td = document.createElement("td");
  td.textContent = text;
  row.append(td);
}

async function renderDashboard(user) {
  const main = document.querySelector("main");
  main.replaceChildren();
  const section = dashboardElement("section", "dashboard");
  const header = dashboardElement("div", "dashboard-head");
  const welcome = document.createElement("div");
  welcome.append(dashboardElement("div", "eyebrow", user.role === "admin" ? "SOLARIS YÖNETİM" : "SOLARIS TOPLULUĞU"));
  const heading = dashboardElement("h1", "", `Merhaba, ${user.name}.`);
  const subtitle = dashboardElement("p", "", user.email);
  welcome.append(heading, subtitle);
  const logout = dashboardElement("button", "button button-dark", "Oturumu kapat");
  logout.addEventListener("click", async () => {
    await api("/api/logout", {});
    location.reload();
  });
  header.append(welcome, logout);
  section.append(header);

  if (location.pathname.startsWith("/admin") && user.role !== "admin") {
    const card = dashboardElement("section", "dashboard-card");
    card.append(dashboardElement("h2", "", "Yönetici erişimi gerekli"));
    card.append(dashboardElement("p", "empty-state", "Bu panel yalnızca Solaris yöneticileri tarafından görüntülenebilir."));
    section.append(card);
    main.append(section);
    return;
  }

  if (user.must_change_password) {
    const card = dashboardElement("section", "dashboard-card");
    card.append(dashboardElement("h2", "", "Yönetici parolasını değiştir"));
    card.append(dashboardElement("p", "auth-intro", "Güvenliğiniz için ilk girişte başlangıç parolasını değiştirmeniz gerekir."));
    const form = document.createElement("form");
    form.className = "auth-form";
    form.innerHTML = `
      <label class="field">Mevcut parola<input name="old_password" type="password" autocomplete="current-password" required></label>
      <label class="field">Yeni parola (en az 10 karakter)<input name="new_password" type="password" minlength="10" autocomplete="new-password" required></label>
      <button class="button button-dark" type="submit">Parolayı güncelle</button>`;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      try {
        const result = await api("/api/change-password", {
          old_password: values.get("old_password"),
          new_password: values.get("new_password"),
        });
        showToast(result.message);
        setTimeout(() => location.reload(), 1200);
      } catch (error) {
        showToast(error.message, true);
      }
    });
    card.append(form);
    section.append(card);
  }

  if (user.role === "admin" && !user.must_change_password) {
    const adminLink = dashboardElement("a", "admin-link", "Yönetici panelini aç →");
    adminLink.href = "/admin";
    welcome.append(adminLink);

    const analyticsCard = dashboardElement("section", "dashboard-card");
    analyticsCard.append(dashboardElement("h2", "", "Ziyaretçi analitiği"));
    const metrics = dashboardElement("div", "analytics-metrics");
    analyticsCard.append(metrics);
    section.append(analyticsCard);

    const card = dashboardElement("section", "dashboard-card");
    const visitsTitle = dashboardElement("div", "dashboard-section-title");
    visitsTitle.append(dashboardElement("h2", "", "Ziyaret geçmişi"));
    card.append(visitsTitle);
    const table = document.createElement("table");
    table.className = "user-table";
    const thead = document.createElement("thead");
    const titleRow = document.createElement("tr");
    ["SAYFA", "IP ADRESİ", "CİHAZ", "TARİH / SAAT"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      titleRow.append(th);
    });
    thead.append(titleRow);
    const tbody = document.createElement("tbody");
    table.append(thead, tbody);
    card.append(table);
    section.append(card);

    const emailsCard = dashboardElement("section", "dashboard-card");
    const emailsTitle = dashboardElement("div", "dashboard-section-title");
    emailsTitle.append(dashboardElement("h2", "", "Doğrulanmış e-posta adresleri"));
    emailsCard.append(emailsTitle);
    const emailTable = document.createElement("table");
    emailTable.className = "user-table";
    const emailHead = document.createElement("thead");
    const emailHeaderRow = document.createElement("tr");
    ["AD", "E-POSTA", "KAYIT TARİHİ"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      emailHeaderRow.append(th);
    });
    emailHead.append(emailHeaderRow);
    const emailBody = document.createElement("tbody");
    emailTable.append(emailHead, emailBody);
    emailsCard.append(emailTable);
    section.append(emailsCard);

    try {
      const data = await api("/api/admin/analytics");
      const labels = [
        ["Aktif ziyaretçi (5 dk)", data.metrics.active_visitors],
        [`Tekil ziyaretçi (${data.retention_days} gün)`, data.metrics.total_visitors],
        [`Sayfa görüntüleme (${data.retention_days} gün)`, data.metrics.total_page_views],
      ];
      labels.forEach(([label, value]) => {
        const metric = dashboardElement("div", "metric-card");
        metric.append(dashboardElement("span", "", label));
        metric.append(dashboardElement("strong", "", String(value)));
        metrics.append(metric);
      });
      visitsTitle.append(dashboardElement("p", "", `En son ${data.visits.length} ziyaret · ${data.retention_days} gün saklama`));
      data.visits.forEach((visit) => {
        const row = document.createElement("tr");
        cell(row, visit.page);
        cell(row, visit.ip_address);
        cell(row, visit.device_type);
        cell(row, new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" }).format(new Date(visit.visited_at * 1000)));
        tbody.append(row);
      });
      emailsTitle.append(dashboardElement("p", "", `Son ${data.verified_emails.length} doğrulanmış hesap`));
      data.verified_emails.forEach((member) => {
        const row = document.createElement("tr");
        cell(row, member.name);
        cell(row, member.email);
        cell(row, new Intl.DateTimeFormat("tr-TR", { dateStyle: "short" }).format(new Date(member.created_at * 1000)));
        emailBody.append(row);
      });
    } catch (error) {
      analyticsCard.append(dashboardElement("p", "auth-message", error.message));
    }
  } else {
    const card = dashboardElement("section", "dashboard-card");
    card.append(dashboardElement("h2", "", "Solaris'e hoş geldin!"));
    card.append(dashboardElement("p", "empty-state", "E-posta adresin doğrulandı. Topluluğun bir parçası olduğun için mutluyuz."));
    section.append(card);
  }
  main.append(section);
}

const consentBanner = document.querySelector("#consent-banner");
const consentKey = "solaris-analytics-consent";

async function trackPageView() {
  try {
    await api("/api/track", { consent: true, page: location.pathname });
  } catch (error) {
    console.warn("Ziyaret analitiği kaydedilemedi:", error);
  }
}

function startHeartbeat() {
  if (heartbeatStarted) return;
  heartbeatStarted = true;
  setInterval(async () => {
    try {
      await api("/api/heartbeat", { consent: true });
    } catch (error) {
      console.warn("Aktif ziyaretçi bilgisi güncellenemedi:", error);
    }
  }, 60_000);
}

if (localStorage.getItem(consentKey) === "accepted") {
  trackPageView();
  startHeartbeat();
} else if (localStorage.getItem(consentKey) !== "rejected") {
  consentBanner.hidden = false;
}

document.querySelectorAll("[data-consent]").forEach((button) => {
  button.addEventListener("click", async () => {
    const accepted = button.dataset.consent === "accept";
    localStorage.setItem(consentKey, accepted ? "accepted" : "rejected");
    consentBanner.hidden = true;
    if (accepted) {
      await trackPageView();
      startHeartbeat();
      return;
    }
    try {
      await api("/api/revoke-analytics", {});
    } catch (error) {
      showToast(`Analitik verileri silinemedi: ${error.message}`, true);
    }
  });
});

document.querySelector(".privacy-settings").addEventListener("click", () => {
  consentBanner.hidden = false;
});

api("/api/me")
  .then(({ user }) => {
    if (user) renderDashboard(user);
    else if (location.pathname.startsWith("/admin")) {
      renderLogin("Yönetici paneli için önce yönetici hesabınızla giriş yapın.");
      openModal();
    }
  })
  .catch((error) => showToast(error.message, true));

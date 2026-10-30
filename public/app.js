const backdrop = document.querySelector("#auth-backdrop");
const content = document.querySelector("#auth-content");
const toast = document.querySelector("#toast");
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
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error("Solaris sunucusundan geçerli yanıt alınamadı. Siteyi `python server.py` ile açın.");
  }
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

function updateNavigation(user) {
  const nav = document.querySelector(".nav-links");
  nav.querySelectorAll(".dynamic-nav-link").forEach((link) => link.remove());
  document.querySelectorAll(".nav-actions [data-authenticated-action]").forEach((button) => button.remove());
  if (!user) return;
  const accountLink = dashboardElement("a", "dynamic-nav-link", "Hesabım");
  accountLink.href = "#account-panel";
  nav.append(accountLink);
  if (user.role === "admin" && !user.must_change_password) {
    const adminLink = dashboardElement("a", "dynamic-nav-link", "Yönetim");
    adminLink.href = "#account-panel";
    nav.append(adminLink);
  }
}

function renderLogin(message = "") {
  content.innerHTML = `
    <h2 id="auth-title">Solaris'e dön.</h2>
    <p class="auth-intro">Minecraft hesabını bağlamak için oyun sunucusundan aldığın tek kullanımlık kodu gir. Oyun parolan istenmez.</p>
    ${message ? `<p class="auth-message">${message}</p>` : ""}
    <form class="auth-form" id="login-form">
      <label class="field">Oyuncu adı<input name="username" autocomplete="username" maxlength="16" required></label>
      <label class="field">Tek kullanımlık kod<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required></label>
      <button class="button button-dark" type="submit">Giriş yap <span>↗</span></button>
    </form>
    <p class="auth-switch">Hesabını henüz bağlamadın mı? <button type="button" data-switch="register">Hesap bağla</button></p>`;
  content.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/minecraft/login", {
        username: String(form.get("username")).trim(),
        code: String(form.get("code")).trim(),
      });
      location.reload();
    } catch (error) {
      renderLogin(error.message);
    }
  });
}

function renderRegister(message = "") {
  content.innerHTML = `
    <h2 id="auth-title">Hesabını bağla.</h2>
    <p class="auth-intro">Önce Minecraft sunucusuna girip hesap bağlama komutunu kullan. Gelen kısa süreli kodu buraya yaz; oyun parolan istenmez.</p>
    ${message ? `<p class="auth-message">${message}</p>` : ""}
    <form class="auth-form" id="register-form">
      <label class="field">Minecraft oyuncu adı<input name="username" autocomplete="username" maxlength="16" required></label>
      <label class="field">Tek kullanımlık bağlama kodu<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required></label>
      <button class="button button-dark" type="submit">Hesabı güvenle bağla <span>↗</span></button>
    </form>
    <p class="auth-switch">Hesabın zaten bağlı mı? <button type="button" data-switch="login">Kodla giriş yap</button></p>`;
  content.querySelector("#register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const result = await api("/api/minecraft/register", {
        username: String(form.get("username")).trim(),
        code: String(form.get("code")).trim(),
      });
      showToast(result.message || "Minecraft hesabın Solaris'e bağlandı.");
      renderLogin();
    } catch (error) {
      renderRegister(error.message);
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
document.querySelector(".nav-links").addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    document.querySelector(".topbar").classList.remove("menu-open");
    menuButton.setAttribute("aria-expanded", "false");
  }
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

function setTable(headers, rows, emptyMessage) {
  const wrapper = dashboardElement("div", "dashboard-scroll");
  const table = dashboardElement("table", "user-table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headers.forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.append(th);
  });
  thead.append(headerRow);
  const tbody = document.createElement("tbody");
  rows.forEach((values) => {
    const row = document.createElement("tr");
    values.forEach((value) => cell(row, String(value || "—")));
    tbody.append(row);
  });
  if (!rows.length) {
    const empty = dashboardElement("p", "empty-state", emptyMessage);
    wrapper.append(empty);
  } else {
    table.append(thead, tbody);
    wrapper.append(table);
  }
  return wrapper;
}

function formatTime(seconds, withTime = true) {
  const options = withTime
    ? { dateStyle: "short", timeStyle: "short" }
    : { dateStyle: "short" };
  return new Intl.DateTimeFormat("tr-TR", options).format(new Date(seconds * 1000));
}

async function renderDashboard(user) {
  updateNavigation(user);
  const main = document.querySelector("main");
  const existing = document.querySelector("#account-panel");
  if (existing) existing.remove();

  const section = dashboardElement("section", "dashboard account-panel");
  section.id = "account-panel";
  const header = dashboardElement("div", "dashboard-head");
  const welcome = document.createElement("div");
  welcome.append(dashboardElement("div", "eyebrow", user.role === "admin" ? "SOLARIS YÖNETİM" : "SOLARIS TOPLULUĞU"));
  welcome.append(dashboardElement("h2", "dashboard-greeting", `Merhaba, ${user.name}.`));
  welcome.append(dashboardElement("p", "", user.email));
  header.append(welcome);
  const logout = dashboardElement("button", "button button-dark", "Oturumu kapat");
  logout.addEventListener("click", async () => {
    try {
      await api("/api/logout", {});
      location.reload();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  header.append(logout);
  section.append(header);

  if (location.pathname.startsWith("/admin") && user.role !== "admin") {
    section.append(dashboardElement("p", "auth-message", "Bu yönetim alanı yalnızca admin hesabına açıktır. Ana menüden Topluluk veya Minecraft sayfalarına geçebilirsiniz."));
    main.prepend(section);
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
  } else if (user.role === "admin") {
    const tabs = dashboardElement("nav", "admin-tabs");
    tabs.setAttribute("aria-label", "Yönetici paneli bölümleri");
    const tabContent = dashboardElement("div", "admin-tab-content");
    const summaryPanel = dashboardElement("section", "admin-tab-panel");
    summaryPanel.dataset.panel = "overview";
    summaryPanel.append(dashboardElement("h2", "", "Genel bakış"));
    const metrics = dashboardElement("div", "analytics-metrics");
    summaryPanel.append(metrics);
    summaryPanel.append(dashboardElement("p", "empty-state", "Aktif ziyaretçi: son 5 dakika içinde görülen tekil ziyaretçiler. Konum tahmini için ziyaretçi IP'si üçüncü taraf servislere gönderilmez."));
    const visitsPanel = dashboardElement("section", "admin-tab-panel");
    visitsPanel.dataset.panel = "visits";
    visitsPanel.append(dashboardElement("h2", "", "Ziyaretler ve kaynak bilgisi"));
    visitsPanel.append(dashboardElement("p", "empty-state", "Şehir/ülke bilgisi GeoIP veritabanı olmadan belirlenemez. Kaynak alanı yönlendiren sitenin alan adını gösterir."));
    const membersPanel = dashboardElement("section", "admin-tab-panel");
    membersPanel.dataset.panel = "members";
    membersPanel.append(dashboardElement("h2", "", "Doğrulanmış e-posta adresleri"));
    tabContent.append(summaryPanel, visitsPanel, membersPanel);
    section.append(tabs, tabContent);

    const tabNames = [
      ["overview", "Genel bakış"],
      ["visits", "Ziyaretler"],
      ["members", "Üyeler"],
    ];
    tabNames.forEach(([name, label], index) => {
      const button = dashboardElement("button", `admin-tab${index === 0 ? " active" : ""}`, label);
      button.type = "button";
      button.dataset.dashboardTab = name;
      button.setAttribute("aria-pressed", String(index === 0));
      tabs.append(button);
    });
    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-dashboard-tab]");
      if (!button) return;
      tabs.querySelectorAll(".admin-tab").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-pressed", String(active));
      });
      tabContent.querySelectorAll(".admin-tab-panel").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== button.dataset.dashboardTab;
      });
    });
    visitsPanel.hidden = true;
    membersPanel.hidden = true;

    try {
      const data = await api("/api/admin/analytics");
      [
        ["Aktif ziyaretçi", data.metrics.active_visitors],
        [`Tekil ziyaretçi · ${data.retention_days} gün`, data.metrics.total_visitors],
        [`Sayfa görüntüleme · ${data.retention_days} gün`, data.metrics.total_page_views],
      ].forEach(([label, value]) => {
        const metric = dashboardElement("div", "metric-card");
        metric.append(dashboardElement("span", "", label));
        metric.append(dashboardElement("strong", "", String(value)));
        metrics.append(metric);
      });
      visitsPanel.append(setTable(
        ["SAYFA", "IP ADRESİ", "CİHAZ", "KAYNAK", "TARAYICI", "DİL", "TARİH / SAAT"],
        data.visits.map((visit) => [
          visit.page,
          visit.ip_address,
          visit.device_type,
          visit.referrer || "Doğrudan",
          visit.user_agent.slice(0, 140),
          visit.language,
          formatTime(visit.visited_at),
        ]),
        "Henüz onaylı analitik ziyareti yok."
      ));
      membersPanel.append(setTable(
        ["AD", "E-POSTA", "KAYIT TARİHİ"],
        data.verified_emails.map((member) => [member.name, member.email, formatTime(member.created_at, false)]),
        "Henüz doğrulanmış üye yok."
      ));
    } catch (error) {
      summaryPanel.append(dashboardElement("p", "auth-message", error.message));
    }
  } else {
    const card = dashboardElement("section", "dashboard-card");
    card.append(dashboardElement("h2", "", "Solaris'e hoş geldin!"));
    card.append(dashboardElement("p", "empty-state", "E-posta adresin doğrulandı. Ana menüden Minecraft dünyasını veya topluluk sayfasını keşfedebilirsin."));
    section.append(card);
  }
  main.prepend(section);
}

const consentBanner = document.querySelector("#consent-banner");
const consentKey = "solaris-analytics-consent";
const themeKey = "solaris-theme";

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = selected;
  document.querySelector(".theme-toggle").textContent = selected === "dark" ? "☀" : "☾";
  document.querySelector(".theme-toggle").setAttribute(
    "aria-label",
    selected === "dark" ? "Açık temaya geç" : "Koyu temaya geç"
  );
  document.querySelector('meta[name="theme-color"]').content = selected === "dark" ? "#171812" : "#fff9e8";
}

const storedTheme = localStorage.getItem(themeKey);
applyTheme(storedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
document.querySelector(".theme-toggle").addEventListener("click", () => {
  const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem(themeKey, nextTheme);
  applyTheme(nextTheme);
});

api("/api/site-config")
  .then((config) => {
    const address = config.minecraft_address || "";
    document.querySelector("#minecraft-address").textContent = address || "Sunucu adresi yakında açıklanacak";
    document.querySelector("#minecraft-version").textContent = address
      ? `Sürüm: ${config.minecraft_version || "Java"}`
      : "Sunucu açılış tarihi ve bağlantı bilgileri yakında.";
    document.querySelector("#copy-address").disabled = !address;
    document.querySelector("#copy-address").dataset.address = address;
  })
  .catch((error) => {
    document.querySelector("#minecraft-address").textContent = "Sunucu bilgisi yüklenemedi";
    showToast(error.message, true);
  });

document.querySelector("#copy-address").addEventListener("click", async (event) => {
  const address = event.currentTarget.dataset.address;
  if (!address) return;
  try {
    await navigator.clipboard.writeText(address);
    showToast("Sunucu adresi kopyalandı.");
  } catch (error) {
    showToast(`Kopyalanamadı: ${error.message}`, true);
  }
});

async function trackPageView() {
  try {
    await api("/api/track", {
      consent: true,
      page: location.pathname + location.hash,
      source: document.referrer,
    });
  } catch (error) {
    console.warn("Ziyaret analitiği kaydedilemedi:", error);
  }
}

window.addEventListener("hashchange", () => {
  if (localStorage.getItem(consentKey) === "accepted") trackPageView();
});

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

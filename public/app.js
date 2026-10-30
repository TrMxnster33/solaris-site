const backdrop = document.querySelector("#auth-backdrop");
const content = document.querySelector("#auth-content");
const toast = document.querySelector("#toast");
const authTabs = [...document.querySelectorAll("[data-auth-tab]")];
let toastTimer;
let currentUser = null;
let heartbeatTimer = null;
let sessionReady = false;

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
    throw new Error("Solaris sunucusundan geçerli yanıt alınamadı.");
  }
  if (!response.ok) throw new Error(result.error || "Bir hata oluştu.");
  return result;
}

function setAuthTab(tab) {
  authTabs.forEach((button) => {
    const active = button.dataset.authTab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  renderAuthForm(tab);
}

function renderAuthForm(tab, message = "") {
  const register = tab === "register";
  content.innerHTML = register
    ? `<h2 id="auth-title">Solaris'e katıl.</h2>
       <p class="auth-intro">Topluluğa özel web hesabını oluştur. Bu parola Minecraft/oyun parolandan bağımsızdır.</p>
       <p class="form-message" role="alert"></p>
       <form class="auth-form" id="register-form">
         <label class="field">E-posta adresi<input name="email" type="email" autocomplete="email" maxlength="254" required></label>
         <label class="field">Minecraft oyuncu adı<input name="username" autocomplete="nickname" minlength="3" maxlength="16" pattern="[A-Za-z0-9_]{3,16}" aria-describedby="username-hint" required><small id="username-hint">3-16 karakter; harf, rakam ve alt çizgi.</small></label>
         <label class="field">Parola<input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></label>
         <label class="field">Parola tekrarı<input name="password_confirm" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></label>
         <button class="button button-primary submit-button" type="submit">Hesap oluştur <span aria-hidden="true">↗</span></button>
       </form>`
    : `<h2 id="auth-title">Tekrar hoş geldin.</h2>
       <p class="auth-intro">E-posta adresin veya Solaris oyuncu adınla giriş yap.</p>
       <p class="form-message" role="alert"></p>
       <form class="auth-form" id="login-form">
         <label class="field">E-posta veya oyuncu adı<input name="email_or_username" autocomplete="username" required></label>
         <label class="field">Parola<input name="password" type="password" autocomplete="current-password" required></label>
         <label class="remember-option"><input name="remember_me" type="checkbox"><span>Beni hatırla</span></label>
         <button class="button button-primary submit-button" type="submit">Giriş yap <span aria-hidden="true">↗</span></button>
       </form>`;

  const messageNode = content.querySelector(".form-message");
  messageNode.textContent = message;
  content.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const submit = formElement.querySelector('[type="submit"]');
    submit.disabled = true;
    messageNode.textContent = "";
    const form = new FormData(formElement);
    try {
      let result;
      if (register) {
        const password = String(form.get("password"));
        if (password !== String(form.get("password_confirm"))) {
          throw new Error("Parolalar eşleşmiyor.");
        }
        result = await api("/api/register", {
          email: String(form.get("email")).trim(),
          username: String(form.get("username")).trim(),
          password,
          password_confirm: String(form.get("password_confirm")),
        });
      } else {
        result = await api("/api/login", {
          email_or_username: String(form.get("email_or_username")).trim(),
          password: String(form.get("password")),
          remember_me: form.get("remember_me") === "on",
        });
      }
      currentUser = result.user;
      sessionReady = true;
      closeModal();
      updateNavigation(currentUser);
      renderAccount(currentUser);
      showToast(register ? "Hesabın oluşturuldu, Solaris'e hoş geldin!" : "Solaris'e tekrar hoş geldin.");
      navigateToView("profile");
    } catch (error) {
      messageNode.textContent = error.message;
      submit.disabled = false;
    }
  });
}

function openModal(tab) {
  setAuthTab(tab);
  backdrop.hidden = false;
  document.body.classList.add("modal-open");
  const firstInput = content.querySelector("input");
  if (firstInput) firstInput.focus();
}

function closeModal() {
  backdrop.hidden = true;
  document.body.classList.remove("modal-open");
}

function makeElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function updateNavigation(user) {
  const actions = document.querySelector(".nav-actions");
  actions.replaceChildren();
  if (!user) {
    const login = makeElement("button", "button button-quiet", "Giriş yap");
    login.type = "button";
    login.dataset.openAuth = "login";
    const register = makeElement("button", "button button-primary", "Hesap oluştur ↗");
    register.type = "button";
    register.dataset.openAuth = "register";
    actions.append(login, register);
    return;
  }
  const account = makeElement("a", "button button-quiet nav-view-link", "Profil");
  account.href = "#profile";
  account.dataset.view = "profile";
  actions.append(account);
  if (user.role === "admin") {
    const admin = makeElement("a", "button button-primary nav-view-link", "Admin paneli");
    admin.href = "#admin";
    admin.dataset.view = "admin";
    actions.append(admin);
  }
}

function renderAccount(user) {
  const section = document.querySelector("#profile-view");
  section.replaceChildren();
  const toolbar = makeElement("div", "dashboard-toolbar");
  const backHome = makeElement("a", "button button-quiet", "← Ana sayfaya dön");
  backHome.href = "#home";
  toolbar.append(backHome);
  const heading = makeElement("div", "account-heading");
  heading.append(
    makeElement("div", "eyebrow", user.role === "admin" ? "SOLARIS YÖNETİM" : "SOLARIS TOPLULUĞU"),
    makeElement("h2", "", "Profilim"),
    makeElement("p", "", `Hoş geldin, ${user.username}. Hesap bilgilerin ve oturum durumun.`),
  );
  const logout = makeElement("button", "button button-quiet logout-button", "Güvenli çıkış");
  logout.type = "button";
  logout.addEventListener("click", async () => {
    logout.disabled = true;
    try {
      await api("/api/logout", {});
      currentUser = null;
      sessionReady = true;
      section.replaceChildren();
      updateNavigation(null);
      showToast("Oturumun güvenli şekilde kapatıldı.");
      navigateToView("home");
    } catch (error) {
      showToast(error.message, true);
      logout.disabled = false;
    }
  });
  const profile = makeElement("article", "profile-card");
  const avatar = makeElement("div", "skin-avatar");
  avatar.setAttribute("aria-label", `${user.username} oyuncu profili`);
  avatar.append(makeElement("span", "", user.username.slice(0, 1).toUpperCase()));
  const profileText = makeElement("div", "profile-copy");
  profileText.append(
    makeElement("span", "profile-status", "● Çevrimiçi"),
    makeElement("h3", "", user.username),
    makeElement("p", "", user.email),
    makeElement("small", "", `Solaris üyesi · ${new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(new Date(user.created_at * 1000))}`),
  );
  profile.append(avatar, profileText);
  const headRow = makeElement("div", "account-topline");
  headRow.append(heading, logout);
  section.append(toolbar, headRow, profile);
}

function navigateToView(view) {
  const hash = `#${view}`;
  if (location.hash === hash) {
    activateCurrentView();
  } else {
    location.hash = view;
  }
}

function activateCurrentView() {
  if (!sessionReady) return;
  let view = location.hash.slice(1);
  if (!["profile", "admin"].includes(view)) view = "home";
  if (view === "profile" && !currentUser) {
    history.replaceState(null, "", "#home");
    view = "home";
    openModal("login");
  } else if (view === "admin" && (!currentUser || currentUser.role !== "admin")) {
    history.replaceState(null, "", "#home");
    view = "home";
    showToast("Admin paneli için yönetici hesabıyla giriş yapmalısın.", true);
  }

  document.querySelector("#home-view").hidden = view !== "home";
  document.querySelector("#profile-view").hidden = view !== "profile";
  document.querySelector("#admin-view").hidden = view !== "admin";
  document.querySelector("#site-footer").hidden = view !== "home";
  document.querySelectorAll(".nav-view-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === view);
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (view === "admin") loadAdminDashboard();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function makeTable(headers, rows, emptyMessage) {
  const wrapper = makeElement("div", "table-scroll");
  if (!rows.length) {
    wrapper.append(makeElement("p", "empty-state", emptyMessage));
    return wrapper;
  }
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headers.forEach((label) => headerRow.append(makeElement("th", "", label)));
  thead.append(headerRow);
  const tbody = document.createElement("tbody");
  rows.forEach((values) => {
    const row = document.createElement("tr");
    values.forEach((value) => row.append(makeElement("td", "", String(value ?? "—"))));
    tbody.append(row);
  });
  table.append(thead, tbody);
  wrapper.append(table);
  return wrapper;
}

function displayTime(timestamp) {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" })
    .format(new Date(timestamp * 1000));
}

function makePagination(currentPage, totalPages, totalItems, label, onNavigate) {
  const nav = makeElement("div", "pagination");
  const previous = makeElement("button", "button button-quiet", "← Önceki");
  previous.type = "button";
  previous.disabled = currentPage <= 1;
  previous.addEventListener("click", () => onNavigate(currentPage - 1));
  const pageText = makeElement("span", "", `${currentPage} / ${totalPages} · ${totalItems} ${label}`);
  const next = makeElement("button", "button button-quiet", "Sonraki →");
  next.type = "button";
  next.disabled = currentPage >= totalPages;
  next.addEventListener("click", () => onNavigate(currentPage + 1));
  nav.append(previous, pageText, next);
  return nav;
}

async function loadAdminDashboard(pages = { visits: 1, users: 1 }) {
  const section = document.querySelector("#admin-view");
  section.replaceChildren();
  section.classList.add("admin-dashboard");
  section.append(
    makeElement("div", "eyebrow", "YÖNETİCİ PANELİ"),
    makeElement("h2", "", "Topluluk görünümü"),
    makeElement("p", "admin-description", "Yalnızca açık analitik izni veren ziyaretçilerin verileri listelenir."),
  );
  const toolbar = makeElement("div", "dashboard-toolbar");
  const backHome = makeElement("a", "button button-quiet", "← Ana sayfaya dön");
  backHome.href = "#home";
  toolbar.append(backHome);
  section.prepend(toolbar);
  const loading = makeElement("p", "empty-state", "Yönetim verileri yükleniyor…");
  section.append(loading);
  try {
    const data = await api(
      `/api/admin/analytics?visits_page=${pages.visits}&users_page=${pages.users}`,
    );
    loading.remove();
    const metrics = makeElement("div", "analytics-metrics");
    [
      ["Şu an aktif", data.metrics.online],
      ["Tekil ziyaretçi", data.metrics.visitors],
      ["Sayfa görüntüleme", data.metrics.page_views],
      ["Kayıtlı hesap", data.metrics.users],
    ].forEach(([label, value]) => {
      const card = makeElement("article", "metric-card");
      card.append(makeElement("span", "", label), makeElement("strong", "", String(value)));
      metrics.append(card);
    });
    section.append(metrics, makeElement("h3", "dashboard-subheading", "Ziyaret kayıtları"));
    section.append(makeElement("p", "admin-description", "Yalnızca analitik izni veren ziyaretçilerin IP, cihaz, kaynak, tarayıcı, dil ve tarih bilgileri gösterilir."));
    section.append(makeTable(
      ["Sayfa", "IP", "Cihaz", "Kaynak", "Tarayıcı", "Dil", "Tarih"],
      data.visits.map((visit) => [
        visit.page, visit.ip_address, visit.device_type, visit.referrer,
        visit.user_agent, visit.language, displayTime(visit.visited_at),
      ]),
      "Henüz izinli ziyaret kaydı yok.",
    ));
    section.append(makePagination(
      data.pagination.visits_page,
      data.pagination.visits_pages,
      data.pagination.visits_total,
      "ziyaret",
      (page) => loadAdminDashboard({ ...pages, visits: page }),
    ));
    section.append(makeElement("h3", "dashboard-subheading", "Tüm kayıtlı hesaplar"));
    section.append(makeElement("p", "admin-description", "Hesap parolaları ve parola hash'leri yönetim panelinde gösterilmez."));
    section.append(makeTable(
      ["ID", "Oyuncu adı", "E-posta", "Rol", "Kayıt tarihi"],
      data.users.map((user) => [
        user.id, user.username, user.email, user.role, displayTime(user.created_at),
      ]),
      "Henüz kayıtlı hesap yok.",
    ));
    section.append(makePagination(
      data.pagination.users_page,
      data.pagination.users_pages,
      data.pagination.users_total,
      "hesap",
      (page) => loadAdminDashboard({ ...pages, users: page }),
    ));
  } catch (error) {
    loading.textContent = error.message;
    loading.classList.add("error-text");
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-auth]");
  if (button) openModal(button.dataset.openAuth);
  const consentButton = event.target.closest("[data-consent]");
  if (consentButton) {
    const accepted = consentButton.dataset.consent === "accept";
    localStorage.setItem("solaris-analytics-consent", accepted ? "accepted" : "rejected");
    document.querySelector("#consent-banner").hidden = true;
    if (accepted) trackCurrentPage();
    else stopHeartbeat();
  }
});

authTabs.forEach((button) => button.addEventListener("click", () => setAuthTab(button.dataset.authTab)));
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
document.querySelector(".nav-actions").addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    document.querySelector(".topbar").classList.remove("menu-open");
    menuButton.setAttribute("aria-expanded", "false");
  }
});
window.addEventListener("hashchange", activateCurrentView);

const themeButton = document.querySelector(".theme-toggle");
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("solaris-theme", theme);
  themeButton.textContent = theme === "dark" ? "☼" : "☾";
  themeButton.setAttribute("aria-label", theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç");
}
themeButton.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
setTheme(localStorage.getItem("solaris-theme") || "dark");

document.querySelector("#copy-address").addEventListener("click", async () => {
  const address = document.querySelector("#minecraft-address").textContent.trim();
  if (!address || address.includes("hazırlanıyor") || address.includes("yakında")) {
    showToast("Sunucu adresi henüz paylaşılmadı.", true);
    return;
  }
  try {
    await navigator.clipboard.writeText(address);
    showToast("Sunucu adresi kopyalandı.");
  } catch {
    showToast("Adres kopyalanamadı; metni seçip kopyalayabilirsin.", true);
  }
});

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}
async function trackCurrentPage() {
  try {
    await api("/api/track", {
      consent: true,
      page: `${location.pathname}${location.hash}`,
      source: document.referrer,
    });
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      api("/api/heartbeat", { consent: true }).catch((error) => console.error(error));
    }, 60_000);
  } catch (error) {
    console.error("Analitik kaydı tamamlanamadı:", error);
  }
}

document.querySelector(".privacy-settings").addEventListener("click", async () => {
  const accepted = localStorage.getItem("solaris-analytics-consent") === "accepted";
  if (accepted) {
    try {
      await api("/api/revoke-analytics", {});
      localStorage.setItem("solaris-analytics-consent", "rejected");
      stopHeartbeat();
      showToast("Analitik izni geri alındı ve ziyaretçi kayıtların silindi.");
    } catch (error) {
      showToast(error.message, true);
    }
  } else {
    localStorage.removeItem("solaris-analytics-consent");
    document.querySelector("#consent-banner").hidden = false;
  }
});

async function initialize() {
  const consent = localStorage.getItem("solaris-analytics-consent");
  if (consent === "accepted") trackCurrentPage();
  else if (!consent) document.querySelector("#consent-banner").hidden = false;
  try {
    const config = await api("/api/site-config");
    const address = config.minecraft_address || "Sunucu adresi yakında";
    document.querySelector("#minecraft-address").textContent = address;
    document.querySelector("#copy-address").disabled = !config.minecraft_address;
    document.querySelector("#minecraft-version").textContent = config.minecraft_version
      ? `Sürüm: ${config.minecraft_version}` : "";
  } catch (error) {
    document.querySelector("#minecraft-address").textContent = "Sunucu bilgisi şu anda alınamıyor.";
    console.error(error);
  }
  try {
    const result = await api("/api/me");
    currentUser = result.user;
    updateNavigation(currentUser);
    if (currentUser) renderAccount(currentUser);
  } catch (error) {
    console.error("Oturum bilgisi alınamadı:", error);
  } finally {
    sessionReady = true;
    activateCurrentView();
  }
}

initialize();

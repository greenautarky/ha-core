/**
 * greenautarky Onboarding Wizard Panel
 *
 * Self-contained web component that runs as a custom HA panel.
 * Normal mode:  GDPR -> Telemetry -> Info -> Done
 * Tenant mode:  Account -> GDPR -> Telemetry -> Info -> Done
 */

const GA_PRIMARY = "#2B5A2A";
const GA_PRIMARY_LIGHT = "#3D7B3B";

const GA_LOGO_SVG = `
<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" class="ga-logo">
  <circle cx="100" cy="100" r="90" fill="${GA_PRIMARY}"/>
  <text x="100" y="115" text-anchor="middle" fill="white"
        font-size="48" font-weight="bold" font-family="Arial,sans-serif">GA</text>
</svg>`;

const HA_LOGO_SVG = `
<svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg" class="ha-logo">
  <path fill="#18BCF2"
    d="M240 224.762a15 15 0 0 1-15 15H15a15 15 0 0 1-15-15v-90c0-8.25 4.77-19.769 10.61-25.609l98.78-98.7805c5.83-5.83 15.38-5.83 21.21 0l98.79 98.7895c5.83 5.83 10.61 17.36 10.61 25.61v90-.01Z"/>
  <path fill="#F2F4F9"
    d="m107.27 239.762-40.63-40.63c-2.09.72-4.32 1.13-6.64 1.13-11.3 0-20.5-9.2-20.5-20.5s9.2-20.5 20.5-20.5 20.5 9.2 20.5 20.5c0 2.33-.41 4.56-1.13 6.65l31.63 31.63v-115.88c-6.8-3.34-11.5-10.32-11.5-18.39 0-11.3 9.2-20.5 20.5-20.5s20.5 9.2 20.5 20.5c0 8.07-4.7 15.05-11.5 18.39v81.27l31.46-31.46c-.62-1.96-.96-4.04-.96-6.2 0-11.3 9.2-20.5 20.5-20.5s20.5 9.2 20.5 20.5-9.2 20.5-20.5 20.5c-2.5 0-4.88-.47-7.09-1.29L129 208.892v30.88z"/>
</svg>`;

class GaOnboardingPanel extends HTMLElement {
  constructor() {
    super();
    this._step = "gdpr";
    this._tenantMode = false;
    this._telemetryPrefs = { error_logs: true, metrics: true };
    this._tenantData = { name: "", username: "", password: "", password2: "" };
    this._error = "";
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._checkStatus();
    }
  }

  get _steps() {
    return this._tenantMode
      ? ["account", "gdpr", "telemetry", "info"]
      : ["gdpr", "telemetry", "info"];
  }

  get _totalSteps() {
    return this._steps.length;
  }

  get _currentStepNum() {
    const idx = this._steps.indexOf(this._step);
    return idx >= 0 ? idx + 1 : 1;
  }

  async _checkStatus() {
    try {
      const resp = await fetch("/api/greenautarky_onboarding/status", {
        headers: { Authorization: `Bearer ${this._hass.auth.data.access_token}` },
      });
      const state = await resp.json();
      if (state.completed) {
        window.location.href = "/";
        return;
      }
      this._tenantMode = !!state.tenant_mode;
      // Resume from last incomplete step
      const done = state.steps_done || [];
      if (done.includes("telemetry")) this._step = "info";
      else if (done.includes("gdpr")) this._step = "telemetry";
      else if (done.includes("account") || !this._tenantMode) this._step = "gdpr";
      else this._step = "account";
    } catch (e) {
      // Start from beginning
    }
    this._render();
  }

  async _apiPost(endpoint, data) {
    const resp = await fetch(`/api/greenautarky_onboarding/${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this._hass.auth.data.access_token}`,
      },
      body: JSON.stringify(data),
    });
    return resp.json();
  }

  async _createAccount() {
    this._error = "";
    const d = this._tenantData;
    if (!d.name || !d.username || !d.password) {
      this._error = "Bitte alle Felder ausfuellen.";
      this._render();
      return;
    }
    if (d.password !== d.password2) {
      this._error = "Die Passwoerter stimmen nicht ueberein.";
      this._render();
      return;
    }
    if (d.password.length < 6) {
      this._error = "Das Passwort muss mindestens 6 Zeichen lang sein.";
      this._render();
      return;
    }
    const result = await this._apiPost("create_tenant", {
      name: d.name,
      username: d.username,
      password: d.password,
    });
    if (result.status === "ok") {
      this._step = "gdpr";
      this._render();
    } else {
      this._error = result.message || "Fehler beim Erstellen des Kontos.";
      this._render();
    }
  }

  async _acceptGDPR() {
    await this._apiPost("gdpr", { accepted: true });
    this._step = "telemetry";
    this._render();
  }

  async _saveTelemetry() {
    await this._apiPost("telemetry", this._telemetryPrefs);
    this._step = "info";
    this._render();
  }

  async _complete() {
    const result = await this._apiPost("complete", {});
    if (result.redirect) {
      window.location.href = result.redirect;
    }
  }

  _render() {
    const progress = this._currentStepNum / this._totalSteps;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--ha-font-family, Roboto, sans-serif);
          color: var(--primary-text-color, #212121);
          background: var(--primary-background-color, #fafafa);
          min-height: 100vh;
        }
        .progress-bar {
          position: fixed; top: 0; left: 0; width: 100%; height: 4px;
          background: #e0e0e0; z-index: 10;
        }
        .progress-fill {
          height: 100%; background: ${GA_PRIMARY};
          transition: width 0.3s ease;
          width: ${progress * 100}%;
        }
        .container { max-width: 480px; margin: 0 auto; padding: 48px 24px; }
        .card {
          background: var(--card-background-color, #fff);
          border-radius: 16px; padding: 32px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .brand-block { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
        .ga-logo { width: 64px; height: 64px; }
        .ha-logo { width: 40px; height: 40px; }
        .brand-tagline { font-size: 13px; color: #5a5a5a; margin: 8px 0 0 0; }
        .brand-tagline strong { color: ${GA_PRIMARY}; }
        h1 { color: ${GA_PRIMARY}; font-size: 1.5rem; margin: 0 0 8px 0; }
        h2 { color: ${GA_PRIMARY}; font-size: 1.1rem; margin: 24px 0 8px 0; }
        h2:first-of-type { margin-top: 16px; }
        p { line-height: 1.5; margin: 8px 0; }
        .step-indicator { font-size: 13px; color: #888; margin-bottom: 16px; }
        .btn-primary {
          display: block; width: 100%; padding: 12px 24px; margin-top: 24px;
          background: ${GA_PRIMARY}; color: white; border: none;
          border-radius: 8px; font-size: 16px; cursor: pointer; font-family: inherit;
        }
        .btn-primary:hover { background: ${GA_PRIMARY_LIGHT}; }
        .btn-primary:disabled { background: #999; cursor: not-allowed; }
        .toggle-row {
          display: flex; justify-content: space-between; align-items: center;
          padding: 12px 0; border-bottom: 1px solid #eee;
        }
        .toggle-row:last-child { border-bottom: none; }
        .toggle-label { flex: 1; }
        .toggle-label .heading { font-weight: 500; font-size: 14px; }
        .toggle-label .description { font-size: 12px; color: #888; margin-top: 2px; }
        .switch { position: relative; width: 48px; height: 28px; flex-shrink: 0; margin-left: 16px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
          position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
          background: #ccc; border-radius: 28px; transition: 0.3s;
        }
        .slider:before {
          content: ""; position: absolute; height: 22px; width: 22px;
          left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s;
        }
        input:checked + .slider { background: ${GA_PRIMARY}; }
        input:checked + .slider:before { transform: translateX(20px); }
        ul { padding-left: 20px; margin: 8px 0; }
        li { margin-bottom: 4px; line-height: 1.4; }
        a { color: ${GA_PRIMARY_LIGHT}; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .gdpr-text {
          max-height: 200px; overflow-y: auto; padding: 12px;
          background: #f5f5f5; border-radius: 8px; font-size: 13px;
          line-height: 1.6; margin: 16px 0;
        }
        .form-field { margin-bottom: 16px; }
        .form-field label {
          display: block; font-size: 13px; font-weight: 500;
          margin-bottom: 4px; color: #555;
        }
        .form-field input {
          width: 100%; padding: 10px 12px; border: 1px solid #ccc;
          border-radius: 8px; font-size: 15px; font-family: inherit;
          box-sizing: border-box;
        }
        .form-field input:focus {
          outline: none; border-color: ${GA_PRIMARY};
          box-shadow: 0 0 0 2px rgba(43,90,42,0.15);
        }
        .error { color: #d32f2f; font-size: 13px; margin-top: 8px; }
      </style>

      <div class="progress-bar"><div class="progress-fill"></div></div>
      <div class="container">
        <div class="card">
          <div class="brand-block">
            ${GA_LOGO_SVG} ${HA_LOGO_SVG}
          </div>
          <p class="brand-tagline">
            <strong>greenautarky KI-Butler</strong> powered by Home Assistant
          </p>
          ${this._renderStep()}
        </div>
      </div>
    `;

    this._attachHandlers();
  }

  _renderStep() {
    switch (this._step) {
      case "account": return this._renderAccount();
      case "gdpr": return this._renderGDPR();
      case "telemetry": return this._renderTelemetry();
      case "info": return this._renderInfo();
      default: return "";
    }
  }

  _renderAccount() {
    return `
      <div class="step-indicator">Schritt ${this._currentStepNum} von ${this._totalSteps}</div>
      <h1>Konto erstellen</h1>
      <p>Erstelle dein persoenliches Benutzerkonto fuer den KI-Butler.</p>

      <div class="form-field">
        <label for="acc-name">Anzeigename</label>
        <input type="text" id="acc-name" placeholder="z.B. Max Mustermann"
               value="${this._tenantData.name}">
      </div>
      <div class="form-field">
        <label for="acc-username">Benutzername</label>
        <input type="text" id="acc-username" placeholder="z.B. max"
               value="${this._tenantData.username}" autocapitalize="none">
      </div>
      <div class="form-field">
        <label for="acc-password">Passwort</label>
        <input type="password" id="acc-password" placeholder="Mindestens 6 Zeichen">
      </div>
      <div class="form-field">
        <label for="acc-password2">Passwort wiederholen</label>
        <input type="password" id="acc-password2" placeholder="Passwort bestaetigen">
      </div>
      ${this._error ? `<div class="error">${this._error}</div>` : ""}
      <button class="btn-primary" id="create-account">Konto erstellen</button>
    `;
  }

  _renderGDPR() {
    return `
      <div class="step-indicator">Schritt ${this._currentStepNum} von ${this._totalSteps}</div>
      <h1>Datenschutz</h1>
      <p>Bevor wir starten, brauchen wir deine Zustimmung zur Datenverarbeitung.</p>

      <div class="gdpr-text">
        <strong>Datenschutzerklaerung</strong><br><br>
        Dein greenautarky KI-Butler verarbeitet personenbezogene Daten
        ausschliesslich lokal auf diesem Geraet. Es werden keine Daten an
        Dritte weitergegeben, es sei denn, du aktivierst dies ausdruecklich
        (z.B. Cloud-Integrationen oder Telemetrie).<br><br>
        <strong>Welche Daten werden verarbeitet?</strong>
        <ul>
          <li>Geraetezustaende und Automatisierungen (lokal gespeichert)</li>
          <li>Benutzerkonto-Informationen (Name, Anmeldedaten)</li>
          <li>Optionale Telemetriedaten (nur mit deiner Zustimmung)</li>
        </ul>
        <strong>Deine Rechte:</strong>
        <ul>
          <li>Auskunft ueber gespeicherte Daten</li>
          <li>Loeschung deines Kontos und aller Daten</li>
          <li>Widerruf der Telemetrie-Zustimmung jederzeit</li>
        </ul>
        Weitere Informationen findest du auf
        <a href="https://greenautarky.com/datenschutz" target="_blank" rel="noreferrer">greenautarky.com/datenschutz</a>.
      </div>

      <button class="btn-primary" id="accept-gdpr">
        Ich stimme zu und moechte fortfahren
      </button>
    `;
  }

  _renderTelemetry() {
    return `
      <div class="step-indicator">Schritt ${this._currentStepNum} von ${this._totalSteps}</div>
      <h1>Telemetrie</h1>
      <p>Hilf uns, deinen KI-Butler zu verbessern. Du kannst diese Einstellungen
         jederzeit unter <strong>Einstellungen</strong> aendern.</p>

      <div class="toggle-row">
        <div class="toggle-label">
          <div class="heading">Fehlerberichte</div>
          <div class="description">Fehlerprotokolle an greenautarky senden</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="tel-errors" ${this._telemetryPrefs.error_logs ? "checked" : ""}>
          <span class="slider"></span>
        </label>
      </div>

      <div class="toggle-row">
        <div class="toggle-label">
          <div class="heading">Metriken</div>
          <div class="description">Systemmetriken an greenautarky senden</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="tel-metrics" ${this._telemetryPrefs.metrics ? "checked" : ""}>
          <span class="slider"></span>
        </label>
      </div>

      <button class="btn-primary" id="save-telemetry">Weiter</button>
    `;
  }

  _renderInfo() {
    return `
      <div class="step-indicator">Schritt ${this._currentStepNum} von ${this._totalSteps}</div>
      <h1>Ueber deinen KI-Butler</h1>
      <p>
        Dein KI-Butler ist ein lokaler Smart-Home-Hub, der deine Daten schuetzt.
        Er unterstuetzt Zigbee-, WLAN- und Ethernet-Geraete.
      </p>
      <ul>
        <li>Alle Automatisierungen laufen lokal auf dem Geraet</li>
        <li>Keine Cloud-Abhaengigkeit erforderlich</li>
        <li>Erweiterbar mit Add-ons und Integrationen</li>
      </ul>

      <h2>Erste Schritte</h2>
      <p>Nach der Einrichtung kannst du:</p>
      <ul>
        <li>Smart-Geraete hinzufuegen unter <strong>Einstellungen &gt; Geraete</strong></li>
        <li>Automatisierungen erstellen unter <strong>Einstellungen &gt; Automatisierungen</strong></li>
        <li>Add-ons installieren unter <strong>Einstellungen &gt; Add-ons</strong></li>
        <li>Dein Dashboard auf der Uebersichtsseite anpassen</li>
      </ul>

      <h2>Lade die App herunter</h2>
      <p>Steuere dein Zuhause von unterwegs mit der Home Assistant App:</p>
      <ul>
        <li><a href="https://play.google.com/store/apps/details?id=io.homeassistant.companion.android" target="_blank" rel="noreferrer">Google Play Store</a></li>
        <li><a href="https://apps.apple.com/app/home-assistant/id1099568401" target="_blank" rel="noreferrer">Apple App Store</a></li>
      </ul>

      <h2>Hilfe benoetigt?</h2>
      <p>
        Besuche die Dokumentation auf
        <a href="https://www.home-assistant.io/docs/" target="_blank" rel="noreferrer">home-assistant.io/docs</a>
        oder wende dich an die Community-Foren.
      </p>

      <button class="btn-primary" id="complete">Einrichtung abschliessen</button>
    `;
  }

  _attachHandlers() {
    const shadow = this.shadowRoot;

    // Account creation form
    const accName = shadow.getElementById("acc-name");
    if (accName) {
      accName.addEventListener("input", (e) => { this._tenantData.name = e.target.value; });
    }
    const accUser = shadow.getElementById("acc-username");
    if (accUser) {
      accUser.addEventListener("input", (e) => { this._tenantData.username = e.target.value; });
    }
    const accPw = shadow.getElementById("acc-password");
    if (accPw) {
      accPw.addEventListener("input", (e) => { this._tenantData.password = e.target.value; });
    }
    const accPw2 = shadow.getElementById("acc-password2");
    if (accPw2) {
      accPw2.addEventListener("input", (e) => { this._tenantData.password2 = e.target.value; });
    }
    const createBtn = shadow.getElementById("create-account");
    if (createBtn) {
      createBtn.addEventListener("click", () => this._createAccount());
    }

    // GDPR
    const acceptBtn = shadow.getElementById("accept-gdpr");
    if (acceptBtn) {
      acceptBtn.addEventListener("click", () => this._acceptGDPR());
    }

    // Telemetry toggles
    const telErrors = shadow.getElementById("tel-errors");
    if (telErrors) {
      telErrors.addEventListener("change", (e) => {
        this._telemetryPrefs.error_logs = e.target.checked;
      });
    }
    const telMetrics = shadow.getElementById("tel-metrics");
    if (telMetrics) {
      telMetrics.addEventListener("change", (e) => {
        this._telemetryPrefs.metrics = e.target.checked;
      });
    }
    const saveBtn = shadow.getElementById("save-telemetry");
    if (saveBtn) {
      saveBtn.addEventListener("click", () => this._saveTelemetry());
    }

    // Complete
    const completeBtn = shadow.getElementById("complete");
    if (completeBtn) {
      completeBtn.addEventListener("click", () => this._complete());
    }
  }
}

customElements.define("ga-onboarding-panel", GaOnboardingPanel);

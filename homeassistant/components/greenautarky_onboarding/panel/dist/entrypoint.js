/**
 * Thin panel wrapper — loads the standalone /greenautarky-setup page in an
 * iframe so app users see the same wizard as browser users.
 */
class GaOnboardingPanel extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100vh; }
        iframe { width: 100%; height: 100%; border: none; }
      </style>
      <iframe src="/greenautarky-setup.html"></iframe>
    `;
  }

  set hass(_hass) {
    // Required by HA panel contract, but we don't need it —
    // the iframe page handles everything via its own REST calls.
  }
}

customElements.define("ga-onboarding-panel", GaOnboardingPanel);

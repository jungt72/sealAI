import { describe, expect, it } from "vitest";

import { expiredKeycloakRecoveryUrl } from "./recovery";

describe("expiredKeycloakRecoveryUrl", () => {
  it("restarts the dashboard login for an expired Keycloak browser transaction", () => {
    const requestUrl = new URL(
      "https://sealingai.com/api/auth/callback/keycloak" +
        "?error=temporarily_unavailable&error_description=authentication_expired&state=stale",
    );

    expect(expiredKeycloakRecoveryUrl(requestUrl)?.toString()).toBe(
      "https://sealingai.com/dashboard/",
    );
  });

  it("uses the configured public origin behind the reverse proxy", () => {
    const internalUrl = new URL(
      "http://0.0.0.0:3000/api/auth/callback/keycloak" +
        "?error=temporarily_unavailable&error_description=authentication_expired",
    );

    expect(
      expiredKeycloakRecoveryUrl(internalUrl, "https://sealingai.com")?.toString(),
    ).toBe("https://sealingai.com/dashboard/");
  });

  it("does not hide unrelated provider or configuration failures", () => {
    expect(
      expiredKeycloakRecoveryUrl(
        new URL(
          "https://sealingai.com/api/auth/callback/keycloak" +
            "?error=access_denied&error_description=denied",
        ),
      ),
    ).toBeNull();
    expect(
      expiredKeycloakRecoveryUrl(
        new URL(
          "https://sealingai.com/api/auth/callback/another" +
            "?error=temporarily_unavailable&error_description=authentication_expired",
        ),
      ),
    ).toBeNull();
  });
});

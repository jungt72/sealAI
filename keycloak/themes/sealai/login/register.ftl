<#import "template.ftl" as layout>
<@layout.registrationLayout displayInfo=false displayMessage=true; section>
  <#if section == "title">
    SealAI – Registrierung
  <#elseif section == "header">
    Account erstellen
  <#elseif section == "form">
    <div class="page">
      <section class="hero">
        <div class="hero__badge">SealAI Access</div>
        <h1>Starker Start: klares Onboarding mit sicheren Defaults.</h1>
        <p class="muted">
          Wir aktivieren PKCE, kurzlebige Sessions und MFA-Ready Accounts. Saubere Fehlermeldungen und barrierearme Felder inklusive.
        </p>
        <div class="chips">
          <span>progressive Profilfelder</span>
          <span>Consent ready</span>
          <span>Security-first</span>
        </div>
      </section>

      <section class="panel">
        <header class="panel__header">
          <p class="eyebrow">Registrierung</p>
          <h2>Neues SealAI Konto anlegen</h2>
          <p class="muted">Nutze deine Arbeitsadresse. Wir verifizieren E-Mail und setzen Passwort-Richtlinien serverseitig durch.</p>
        </header>

        <#if message?has_content>
          <div class="alert ${message.type!'info'}" role="alert">
            ${kcSanitize(message.summary)}
          </div>
        </#if>

        <form id="kc-register-form" class="form" action="${url.registrationAction}" method="post">
          <div class="field <#if messagesPerField.existsError('firstName','lastName')>field-error</#if>">
            <label for="firstName">Vorname</label>
            <input tabindex="1"
                   id="firstName"
                   name="firstName"
                   value="${(register.formData.firstName!'')}"
                   type="text"
                   autocomplete="given-name"
                   aria-invalid="<#if messagesPerField.existsError('firstName')>true</#if>"/>
            <#if messagesPerField.existsError('firstName')>
              <p class="error">${kcSanitize(messagesPerField.getFirstError('firstName'))?no_esc}</p>
            </#if>
          </div>

          <div class="field <#if messagesPerField.existsError('lastName')>field-error</#if>">
            <label for="lastName">Nachname</label>
            <input tabindex="2"
                   id="lastName"
                   name="lastName"
                   value="${(register.formData.lastName!'')}"
                   type="text"
                   autocomplete="family-name"
                   aria-invalid="<#if messagesPerField.existsError('lastName')>true</#if>"/>
            <#if messagesPerField.existsError('lastName')>
              <p class="error">${kcSanitize(messagesPerField.getFirstError('lastName'))?no_esc}</p>
            </#if>
          </div>

          <div class="field <#if messagesPerField.existsError('email')>field-error</#if>">
            <label for="email">Geschäftliche E-Mail</label>
            <input tabindex="3"
                   id="email"
                   name="email"
                   value="${(register.formData.email!'')}"
                   type="email"
                   autocomplete="email"
                   aria-invalid="<#if messagesPerField.existsError('email')>true</#if>"/>
            <#if messagesPerField.existsError('email')>
              <p class="error">${kcSanitize(messagesPerField.getFirstError('email'))?no_esc}</p>
            </#if>
          </div>

          <#if !usernameHidden??>
            <div class="field <#if messagesPerField.existsError('username')>field-error</#if>">
              <label for="username">Benutzername</label>
              <input tabindex="4"
                     id="username"
                     name="username"
                     value="${(register.formData.username!'')}"
                     type="text"
                     autocomplete="username"
                     aria-invalid="<#if messagesPerField.existsError('username')>true</#if>"/>
              <#if messagesPerField.existsError('username')>
                <p class="error">${kcSanitize(messagesPerField.getFirstError('username'))?no_esc}</p>
              </#if>
            </div>
          </#if>

          <div class="field <#if messagesPerField.existsError('password','password-confirm')>field-error</#if>">
            <label for="password">Passwort</label>
            <input tabindex="5"
                   id="password"
                   name="password"
                   type="password"
                   autocomplete="new-password"
                   aria-invalid="<#if messagesPerField.existsError('password')>true</#if>"/>
          </div>

          <div class="field <#if messagesPerField.existsError('password-confirm')>field-error</#if>">
            <label for="password-confirm">Passwort bestätigen</label>
            <input tabindex="6"
                   id="password-confirm"
                   name="password-confirm"
                   type="password"
                   autocomplete="new-password"
                   aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"/>
            <#if messagesPerField.existsError('password','password-confirm')>
              <p class="error">${kcSanitize(messagesPerField.getFirstError('password','password-confirm'))?no_esc}</p>
            </#if>
          </div>

          <#if termsAcceptanceRequired?? && termsAcceptanceRequired>
            <label class="checkbox">
              <input tabindex="7"
                     id="termsAccepted"
                     name="termsAccepted"
                     type="checkbox"
                     value="true"
                     <#if register.formData?has_content && register.formData.termsAccepted??>checked</#if>/>
              Ich akzeptiere die Nutzungsbedingungen & Datenschutzbestimmungen.
            </label>
          </#if>

          <#if recaptchaRequired??>
            <div class="field">
              <div class="g-recaptcha" data-size="compact" data-sitekey="${recaptchaSiteKey}"></div>
            </div>
          </#if>

          <button tabindex="8" class="cta" type="submit" id="kc-register">Konto erstellen</button>
        </form>

        <div class="panel__footer">
          <p class="muted">Bereits ein Konto? <a class="link" href="${url.loginUrl}">Zur Anmeldung</a></p>
        </div>
      </section>
    </div>
  </#if>
</@layout.registrationLayout>

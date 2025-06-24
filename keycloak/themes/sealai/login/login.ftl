<#import "template.ftl" as layout>
<@layout.registrationLayout; section>
<html lang="${locale.currentLanguageTag}">
<head>
  <meta charset="utf-8">
  <title>SEALAI Login</title>
  <style>
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #f2f2f7;
      height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .login-container {
      background: white;
      border-radius: 20px;
      padding: 2rem;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
      max-width: 400px;
      width: 90%;
      text-align: center;
    }
    h1 {
      font-weight: 600;
      font-size: 1.5rem;
      margin-bottom: 1rem;
    }
    input {
      width: 100%;
      padding: 0.75rem;
      margin-top: 1rem;
      margin-bottom: 1rem;
      border-radius: 8px;
      border: 1px solid #ccc;
      font-size: 1rem;
    }
    button {
      width: 100%;
      padding: 0.75rem;
      background: #0071e3;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      cursor: pointer;
      margin-top: 1rem;
    }
    button:hover {
      background: #005bb5;
    }
    .links {
      margin-top: 1rem;
      font-size: 0.9rem;
      color: #555;
    }
  </style>
</head>
<body>
  <div class="login-container">
    <h1>SEALAI Login</h1>
    <form id="kc-form-login" action="${url.loginAction}" method="post">
      <input id="username" name="username" type="text" placeholder="E-Mail oder Benutzername" autofocus autocomplete="username" />
      <input id="password" name="password" type="password" placeholder="Passwort" autocomplete="current-password" />
      <button type="submit">Anmelden</button>
    </form>
    <div class="links">
      <#if realm.registrationAllowed>
        <a href="${url.registrationUrl}">Neuen Account erstellen</a><br/>
      </#if>
      <#if realm.resetPasswordAllowed>
        <a href="${url.loginResetCredentialsUrl}">Passwort vergessen?</a>
      </#if>
    </div>
  </div>
</body>
</html>
</@layout.registrationLayout>

<#import "template.ftl" as layout>
<#import "field.ftl" as field>
<#import "buttons.ftl" as buttons>
<#import "passkeys.ftl" as passkeys>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('password'); section>
<!-- template: login-password.ftl -->
    <#if section = "header">
        ${msg("sealaiPasswordTitle")}
    <#elseif section = "form">
        <p class="sealai-b2b-lead">${msg("sealaiPasswordLead")}</p>
        <#if auth?has_content && auth.showUsername()>
            <div class="sealai-b2b-context">
                <strong>Workspace identity</strong>
                ${auth.attemptedUsername}
            </div>
        </#if>
        <div id="kc-form">
            <div id="kc-form-wrapper">
                <form id="kc-form-login" class="${properties.kcFormClass!}" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
                    <@field.password name="password" label=msg("password") forgotPassword=realm.resetPasswordAllowed autofocus=true autocomplete="current-password" />
                    <@buttons.actionGroup>
                        <@buttons.button id="kc-login" name="login" label="sealaiSignIn" class=["kcButtonPrimaryClass", "kcButtonBlockClass"] />
                    </@buttons.actionGroup>
                </form>
            </div>
        </div>
        <@passkeys.conditionalUIData />
    </#if>

</@layout.registrationLayout>

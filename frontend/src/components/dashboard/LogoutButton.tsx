"use client";

import { LogOut } from "lucide-react";
import { signOut, useSession } from "next-auth/react";

interface LogoutButtonProps {
    showLabel?: boolean;
}

export default function LogoutButton({ showLabel = true }: LogoutButtonProps) {
    const { data: session } = useSession();

    const handleLogout = async () => {
        // 1. Construct the Keycloak End Session URL
        const keycloakLogoutUrl = new URL("https://auth.sealai.net/realms/sealAI/protocol/openid-connect/logout");

        const idToken = (session as any)?.idToken;

        if (idToken) {
            keycloakLogoutUrl.searchParams.append("id_token_hint", idToken);
            keycloakLogoutUrl.searchParams.append("post_logout_redirect_uri", window.location.origin);
        }

        // 2. Manual Cookie Purge (Hard Clear)
        const cookies = [
            "authjs.session-token",
            "next-auth.session-token",
            "__Secure-authjs.session-token",
            "__Secure-next-auth.session-token"
        ];
        cookies.forEach(name => {
            document.cookie = `${name}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;`;
            document.cookie = `${name}=; Path=/; Domain=${window.location.hostname}; Expires=Thu, 01 Jan 1970 00:00:01 GMT;`;
        });

        // 3. Clear the NextAuth session locally
        await signOut({ redirect: false });

        // 4. Redirect to Keycloak for federated logout
        window.location.href = keycloakLogoutUrl.toString();
    };

    return (
        <button
            onClick={handleLogout}
            className={`flex w-full items-center rounded-xl px-3 py-2.5 text-sm font-medium transition-all group relative ${showLabel
                    ? "text-seal-ylnmn hover:text-red-500 hover:bg-red-50"
                    : "justify-center text-seal-ylnmn hover:text-red-500 hover:bg-red-50"
                }`}
            title={!showLabel ? "Logout" : undefined}
        >
            <LogOut className={`${showLabel ? "mr-3" : ""} h-5 w-5 shrink-0`} />
            {showLabel && <span className="animate-in fade-in duration-300">Sign Out</span>}
            {!showLabel && (
                <div className="absolute left-full ml-4 px-2 py-1 bg-seal-rich text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-[100] whitespace-nowrap">
                    Logout
                </div>
            )}
        </button>
    );
}

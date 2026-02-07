import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth/next";
import { getToken } from "next-auth/jwt";

import { getAuthOptions } from "../../lib/auth-options";
import RagAdminClient from "./RagAdminClient";

export const dynamic = "force-dynamic";

function extractRolesFromJwtPayload(payload: any): Set<string> {
  const roles = new Set<string>();

  const addRoles = (value: any) => {
    if (Array.isArray(value)) {
      for (const r of value) roles.add(String(r));
    }
  };

  // Keycloak realm roles: realm_access.roles
  addRoles(payload?.realm_access?.roles);

  // Keycloak client roles: resource_access.{client}.roles
  const ra = payload?.resource_access;
  if (ra && typeof ra === "object") {
    for (const v of Object.values(ra)) {
      addRoles((v as any)?.roles);
    }
  }

  return roles;
}

const getAccessTokenAndRoles = async (): Promise<{
  accessToken: string | null;
  roleSet: Set<string>;
}> => {
  const cookieHeader = cookies()
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");

  const token = await getToken({
    req: { headers: { cookie: cookieHeader } } as any,
    secret: process.env.NEXTAUTH_SECRET,
  });

  if (!token || typeof token !== "object") {
    return { accessToken: null, roleSet: new Set() };
  }

  const accessToken =
    typeof (token as any).accessToken === "string"
      ? (token as any).accessToken
      : typeof (token as any).access_token === "string"
        ? (token as any).access_token
        : null;

  // In vielen NextAuth+Keycloak Setups liegen die Keycloak Claims direkt auf dem Token-Objekt.
  const roleSet = extractRolesFromJwtPayload(token);

  return { accessToken: accessToken ?? null, roleSet };
};

export default async function RagAdminPage() {
  const authOptions = await getAuthOptions();
  const session = await getServerSession(authOptions);

  if (!session) {
    redirect("/auth/signin?callbackUrl=/rag");
  }

  const { accessToken, roleSet } = await getAccessTokenAndRoles();

  if (!accessToken) {
    redirect("/auth/signin?callbackUrl=/rag");
  }

  if (!roleSet.has("admin")) {
    redirect("/dashboard");
  }

  return <RagAdminClient token={accessToken} />;
}

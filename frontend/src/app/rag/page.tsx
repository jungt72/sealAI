import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth/next";
import { getToken } from "next-auth/jwt";

import { getAuthOptions } from "@/lib/auth-options";
import { getRolesFromAccessToken } from "@/lib/authz";
import RagAdminClient from "./RagAdminClient";

export const dynamic = "force-dynamic";

const getAccessToken = async (): Promise<string | null> => {
  const cookieHeader = cookies()
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");

  const token = await getToken({
    req: { headers: { cookie: cookieHeader } } as any,
    secret: process.env.NEXTAUTH_SECRET,
  });

  if (!token || typeof token !== "object") return null;
  const accessToken =
    typeof (token as any).accessToken === "string"
      ? (token as any).accessToken
      : typeof (token as any).access_token === "string"
        ? (token as any).access_token
        : null;
  return accessToken ?? null;
};

export default async function RagAdminPage() {
  const authOptions = await getAuthOptions();
  const session = await getServerSession(authOptions);

  if (!session) {
    redirect("/auth/signin?callbackUrl=/rag");
  }

  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect("/auth/signin?callbackUrl=/rag");
  }

  const { roleSet } = getRolesFromAccessToken(accessToken);
  if (!roleSet.has("admin")) {
    redirect("/dashboard");
  }

  return <RagAdminClient token={accessToken} />;
}

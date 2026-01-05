import type { NextApiRequest, NextApiResponse } from "next";
import NextAuth from "next-auth";
import { getAuthOptions } from "@/lib/auth-options";

export default async function auth(req: NextApiRequest, res: NextApiResponse) {
  try {
    const authOptions = await getAuthOptions();
    return NextAuth(req, res, authOptions);
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error("[nextauth][fatal]", { name: err.name, message: err.message });
    throw err;
  }
}

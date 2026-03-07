import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    error?: string | null;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    jti?: string | null;
    error?: string | null;
  }
}

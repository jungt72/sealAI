// frontend/src/middleware.ts
import { withAuth } from "next-auth/middleware"

export default withAuth({
  callbacks: {
    authorized({ token }) {
      return !!token?.accessToken
    },
  },
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/api/protected/:path*",
  ],
}

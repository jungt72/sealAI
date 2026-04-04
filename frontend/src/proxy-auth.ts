export function isProtectedPath(pathname: string): boolean {
  return pathname.startsWith("/dashboard") || pathname.startsWith("/rag");
}

export function shouldRedirectToSignIn(pathname: string, isLoggedIn: boolean): boolean {
  return isProtectedPath(pathname) && !isLoggedIn;
}

import SignInClient from "./SignInClient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type SearchParams = { callbackUrl?: string; provider?: string };

export default function SignIn({ searchParams }: { searchParams?: SearchParams }) {
  return <SignInClient callbackUrl={searchParams?.callbackUrl} provider={searchParams?.provider} />;
}

import SignInClient from "./SignInClient";

type SearchParams = { callbackUrl?: string; provider?: string };

export default function SignIn({ searchParams }: { searchParams?: SearchParams }) {
  return <SignInClient callbackUrl={searchParams?.callbackUrl} provider={searchParams?.provider} />;
}

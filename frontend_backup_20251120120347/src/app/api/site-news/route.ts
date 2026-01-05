import { NextResponse } from 'next/server';

const STRAPI_NEWS_PATH =
  '/api/test-entries?publicationState=live&sort=publishedAt:desc&pagination[pageSize]=5';

const resolveStrapiBase = (): string => {
  const candidates = [
    process.env.STRAPI_API_BASE,
    process.env.NEXT_PUBLIC_STRAPI_URL,
    process.env.STRAPI_URL,
  ].filter(Boolean) as string[];

  const base = candidates.length > 0 ? candidates[0]! : 'http://strapi:1337';
  return base.replace(/\/$/, '');
};

export async function GET() {
  const endpoint = `${resolveStrapiBase()}${STRAPI_NEWS_PATH}`;

  try {
    const res = await fetch(endpoint, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      throw new Error(`Strapi responded with status ${res.status}`);
    }

    const payload = await res.json();
    return NextResponse.json(payload);
  } catch (error) {
    console.error('Failed to load Strapi site news', error);
    return NextResponse.json(
      { data: [], error: 'strapi_unreachable' },
      {
        status: 200,
        headers: {
          'Cache-Control': 'no-store',
        },
      },
    );
  }
}

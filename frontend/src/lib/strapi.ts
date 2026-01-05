import { LandingPageData } from './types';
import { mockData } from './mockData';

const STRAPI_URL = process.env.NEXT_PUBLIC_STRAPI_URL || 'http://localhost:1337';
const IMAGE_BASE_URL = process.env.NEXT_PUBLIC_IMAGE_BASE_URL || STRAPI_URL;
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === 'true';
let strapiUnavailableLogged = false;

export async function getNavbarData() {
    if (USE_MOCK) return mockData.global.navbar;
    try {
        const res = await fetch(`${STRAPI_URL}/api/navbar?populate=*`, { next: { revalidate: 60 } });
        if (!res.ok) throw new Error('Failed to fetch navbar');
        const json = await res.json();
        return json.data.attributes;
    } catch (error) {
        console.error('Error fetching navbar:', error);
        return { logo: '', brand_name: '', navigation_links: [] };
    }
}

export async function getLandingPageData(): Promise<LandingPageData> {
    if (USE_MOCK) {
        console.log('Using mock data');
        // Simulate network delay
        await new Promise((resolve) => setTimeout(resolve, 100));
        return {
            global: mockData.global,
            homepage: mockData.homepage || mockData // Fallback if mockData is flat
        } as any;
    }

    console.log(`Fetching data from Strapi at ${STRAPI_URL}...`);
    try {
        const heroUrl = `${STRAPI_URL}/api/hero?populate=*`;
        console.log(`Fetching Hero from: ${heroUrl}`);

        // Fetch all required data in parallel
        const [heroRes, sectionsRes, featuresRes, nextStepsRes, communityRes, navbarRes, introHeadlineRes, productTabsRes] = await Promise.all([
            fetch(heroUrl, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/sections?populate=*`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/features?populate=*`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/next-steps?populate=*`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/community-conference?populate=*`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/navbar?populate=*`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/intro-headline`, { next: { revalidate: 60 } }),
            fetch(`${STRAPI_URL}/api/product-tabs?populate[accordionItems]=*&populate[image]=*&sort=order:asc`, { next: { revalidate: 60 } }),
        ]);

        console.log(`Hero Response Status: ${heroRes.status}`);

        // Helper to parse response
        const parse = async (res: Response, name: string) => {
            if (!res.ok) {
                const text = await res.text();
                const isStrapiUnavailable =
                    res.status === 502 ||
                    text.includes('Strapi public API is not configured in this stack.');
                if (isStrapiUnavailable) {
                    if (!strapiUnavailableLogged) {
                        console.info('Strapi unavailable; using mock data for landing content.');
                        strapiUnavailableLogged = true;
                    }
                    return null;
                }
                console.error(`Failed to fetch ${name}: ${res.status} ${res.statusText}`);
                console.error(`Error body for ${name}:`, text);
                return null;
            }
            const json = await res.json();
            // console.log(`Raw JSON for ${name}:`, JSON.stringify(json).substring(0, 200) + "...");
            return json.data;
        };

        const [hero, sections, features, nextSteps, community, navbarRaw, introHeadline, productTabs] = await Promise.all([
            parse(heroRes, 'hero'),
            parse(sectionsRes, 'sections'),
            parse(featuresRes, 'features'),
            parse(nextStepsRes, 'nextSteps'),
            parse(communityRes, 'community'),
            navbarRes.ok ? navbarRes.json() : Promise.resolve(null),
            parse(introHeadlineRes, 'intro-headline'),
            parse(productTabsRes, 'product-tabs'),
        ]);

        // Extract navbar data from single type response
        const navbar = navbarRaw?.data?.attributes || navbarRaw?.data || null;
        console.log('Fetched Navbar Data:', JSON.stringify(navbar, null, 2));
        console.log('Fetched Hero Data:', JSON.stringify(hero, null, 2));

        const getImageUrl = (image: any) => {
            if (!image?.url) return null;
            if (image.url.startsWith('http')) return image.url;
            return `${IMAGE_BASE_URL}${image.url}`;
        };

        // Construct Homepage Data
        const homepageData = {
            hero: {
                id: hero?.id || 1,
                title: hero?.title || mockData.homepage.hero.title,
                subtitle: hero?.subtitle || mockData.homepage.hero.subtitle,
                cta_text: hero?.cta_text || mockData.homepage.hero.cta_text,
                cta_link: hero?.cta_link || mockData.homepage.hero.cta_link,
                secondary_cta_text: hero?.secondary_cta_text,
                secondary_cta_link: hero?.secondary_cta_link,
                trust_indicators: hero?.trust_indicators,
                background_image: hero?.background_image
                    ? {
                        url: getImageUrl(hero.background_image) || mockData.homepage.hero.background_image?.url || '',
                        alternativeText: hero.background_image.alternativeText || '',
                        width: hero.background_image.width,
                        height: hero.background_image.height,
                    }
                    : mockData.homepage.hero.background_image,
                staticText: hero?.staticText,
                dynamicKeywords: hero?.dynamicKeywords?.map((k: any) => k.text) || [],
            },
            introHeadline: introHeadline?.text || mockData.homepage.introHeadline || 'SealAI revolutioniert die Dichtungstechnik mit KI-gestützter Beratung und präzisen Empfehlungen.',
            productTabs: (productTabs && productTabs.length > 0)
                ? productTabs.map((tab: any) => ({
                    id: tab.id,
                    title: tab.title,
                    accordionItems: (tab.accordionItems || []).map((item: any) => ({
                        id: item.id,
                        title: item.title,
                        description: item.description,
                        link: item.link,
                    })),
                    image: tab.image ? {
                        url: getImageUrl(tab.image) || '',
                        alternativeText: tab.image.alternativeText || '',
                        width: tab.image.width,
                        height: tab.image.height,
                    } : null,
                }))
                : mockData.homepage.productTabs,
            contentSections: (sections && sections.length > 0)
                ? sections.map((s: any) => ({
                    id: s.id,
                    title: s.title,
                    subtitle: s.content, // Mapping content to subtitle as per ImageTextBlock
                    image: {
                        url: getImageUrl(s.image) || '',
                        alternativeText: s.image?.alternativeText || '',
                        width: s.image?.width,
                        height: s.image?.height,
                    },
                    image_position: s.image_position,
                    background_color: 'white', // Default
                }))
                : mockData.homepage.contentSections,
            features: (features && features.length > 0)
                ? features.map((f: any) => ({
                    id: f.id,
                    title: f.title,
                    description: f.description,
                    icon: f.icon,
                }))
                : mockData.homepage.features,
            nextSteps: (nextSteps && nextSteps.length > 0)
                ? nextSteps.map((n: any) => ({
                    id: n.id,
                    title: n.title,
                    description: n.description,
                    cta_text: n.cta_text,
                    cta_link: n.cta_link,
                    image: {
                        url: getImageUrl(n.image) || '',
                        alternativeText: n.image?.alternativeText || '',
                        width: n.image?.width,
                        height: n.image?.height,
                    },
                }))
                : mockData.homepage.nextSteps,
            community: community
                ? {
                    title: community.title,
                    description: community.description,
                    cta_text: community.cta_text,
                    cta_link: community.cta_link,
                    image: {
                        url: getImageUrl(community.image) || mockData.homepage.community.image?.url || '',
                        alternativeText: community.image?.alternativeText || '',
                        width: community.image?.width,
                        height: community.image?.height,
                    },
                }
                : mockData.homepage.community,
        };

        // Construct Global Data
        const globalData = {
            id: 1,
            siteName: 'SealAI',
            navbar: navbar ? {
                id: navbar.id || 1,
                logo: navbar.logo ? {
                    url: getImageUrl(navbar.logo) || '',
                    alternativeText: navbar.logo.alternativeText || '',
                    width: navbar.logo.width,
                    height: navbar.logo.height,
                } : undefined,
                brand_name: navbar.brand_name || 'SEALAI',
                items: (navbar.items || []).map((item: any) => ({
                    id: item.id,
                    label: item.label,
                    href: item.href,
                    isExternal: item.isExternal || false,
                })),
                show_search: navbar.show_search !== undefined ? navbar.show_search : true,
                show_menu: navbar.show_menu !== undefined ? navbar.show_menu : true,
            } : {
                id: 1,
                brand_name: 'SEALAI',
                items: [],
                show_search: true,
                show_menu: true,
            },
            navbarLinks: [],
            footerColumns: [],
            footerBottomLinks: [],
            copyrightText: '?? 2024 SealAI. All rights reserved.',
            sectionNavItems: [
                { id: 1, label: 'Produkte', href: '#products', isExternal: false },
                { id: 2, label: 'Features', href: '#features', isExternal: false },
                { id: 3, label: 'Community', href: '#community', isExternal: false },
                { id: 4, label: 'N??chste Schritte', href: '#next-steps', isExternal: false },
            ],
        };

        return {
            global: globalData,
            homepage: homepageData as any,
        };

    } catch (error) {
        console.error('Error fetching data from Strapi:', error);
        return {
            global: mockData.global || {},
            homepage: mockData.homepage || mockData
        } as any;
    }
}

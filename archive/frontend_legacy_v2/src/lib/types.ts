export interface Image {
    id?: number;
    url: string;
    alternativeText?: string;
    width?: number;
    height?: number;
}

export interface Link {
    id: number;
    label: string;
    href: string;
    isExternal: boolean;
}

export interface AccordionItem {
    id: number;
    title: string;
    description: string;
    link?: string;
}

export interface FooterColumn {
    id: number;
    title: string;
    links: Link[];
}

export interface NavbarData {
    id: number;
    logo?: Image;
    brand_name: string;
    items: Link[];
    show_search: boolean;
    show_menu: boolean;
}

export interface Global {
    id: number;
    siteName: string;
    logo?: Image;
    navbar: NavbarData;
    navbarLinks: Link[];
    footerColumns: FooterColumn[];
    footerBottomLinks: Link[];
    copyrightText: string;
    sectionNavItems: Link[];
}

// --- Unified Homepage Components ---

export interface HeroSection {
    id: number;
    title: string;
    subtitle: string;
    cta_text: string;
    cta_link: string;
    secondary_cta_text?: string;
    secondary_cta_link?: string;
    trust_indicators?: string[];
    background_image?: Image;
    staticText?: string;
    dynamicKeywords?: string[];
}

export interface ProductTabSection {
    id: number;
    title: string;
    image?: Image;
    accordionItems: AccordionItem[];
}

export interface ImageTextSection {
    id: number;
    title: string;
    subtitle: string;
    image?: Image;
    image_position: 'left' | 'right';
    background_color: string;
}

export interface FeatureSection {
    id: number;
    title: string;
    description: string;
    icon: string;
}

export interface CommunitySection {
    id: number;
    title: string;
    description: string;
    cta_text: string;
    cta_link: string;
    image?: Image;
}

export interface NextStepSection {
    id: number;
    title: string;
    description: string;
    cta_text: string;
    cta_link: string;
    image?: Image;
}

// Aliases for backward compatibility with existing components
export type Section = ImageTextSection;
export type Feature = FeatureSection;
export type CommunityConference = CommunitySection;
export type NextStep = NextStepSection;
export type Hero = HeroSection;

export interface HomepageData {
    hero: HeroSection;
    introHeadline: string;
    productTabs: ProductTabSection[];
    contentSections: ImageTextSection[];
    features: FeatureSection[];
    community: CommunitySection;
    nextSteps: NextStepSection[];
}

export interface LandingPageData {
    global: Global;
    homepage: HomepageData;
}


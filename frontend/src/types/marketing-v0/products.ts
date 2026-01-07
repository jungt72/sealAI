export interface Feature {
  title: string;
  description: string;
  link: string;
}

export interface Product {
  id: string;
  name: string;
  image: string;
  features: Feature[];
}

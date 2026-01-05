#!/bin/bash

# Create Strapi content type schemas directory
mkdir -p /root/sealai/strapi/src/api
mkdir -p /root/sealai/strapi/src/components/shared

# --- Components ---

# Create Link Component
cat > /root/sealai/strapi/src/components/shared/link.json << 'EOF'
{
  "collectionName": "components_shared_links",
  "info": {
    "displayName": "Link",
    "icon": "link"
  },
  "options": {},
  "attributes": {
    "label": {
      "type": "string",
      "required": true
    },
    "href": {
      "type": "string",
      "required": true
    },
    "isExternal": {
      "type": "boolean",
      "default": false
    }
  }
}
EOF

# Create Accordion Item Component
cat > /root/sealai/strapi/src/components/shared/accordion-item.json << 'EOF'
{
  "collectionName": "components_shared_accordion_items",
  "info": {
    "displayName": "Accordion Item",
    "icon": "list"
  },
  "options": {},
  "attributes": {
    "title": {
      "type": "string",
      "required": true
    },
    "description": {
      "type": "text",
      "required": true
    },
    "link": {
      "type": "string"
    }
  }
}
EOF

# Create Footer Column Component
cat > /root/sealai/strapi/src/components/shared/footer-column.json << 'EOF'
{
  "collectionName": "components_shared_footer_columns",
  "info": {
    "displayName": "Footer Column",
    "icon": "columns"
  },
  "options": {},
  "attributes": {
    "title": {
      "type": "string",
      "required": true
    },
    "links": {
      "type": "component",
      "repeatable": true,
      "component": "shared.link"
    }
  }
}
EOF

# --- Content Types ---

# Create Global (Single Type)
mkdir -p /root/sealai/strapi/src/api/global/content-types/global
cat > /root/sealai/strapi/src/api/global/content-types/global/schema.json << 'EOF'
{
  "kind": "singleType",
  "collectionName": "globals",
  "info": {
    "singularName": "global",
    "pluralName": "globals",
    "displayName": "Global",
    "description": "Global site settings like Navbar and Footer"
  },
  "options": {
    "draftAndPublish": true
  },
  "pluginOptions": {},
  "attributes": {
    "siteName": {
      "type": "string",
      "default": "SealAI"
    },
    "logo": {
      "type": "media",
      "multiple": false,
      "required": false,
      "allowedTypes": ["images"]
    },
    "navbarLinks": {
      "type": "component",
      "repeatable": true,
      "component": "shared.link"
    },
    "footerColumns": {
      "type": "component",
      "repeatable": true,
      "component": "shared.footer-column"
    },
    "footerBottomLinks": {
      "type": "component",
      "repeatable": true,
      "component": "shared.link"
    },
    "copyrightText": {
      "type": "string",
      "default": "SealAI GmbH. Alle Rechte vorbehalten."
    },
    "sectionNavItems": {
      "type": "component",
      "repeatable": true,
      "component": "shared.link"
    }
  }
}
EOF

# Create Product Tab (Collection Type)
mkdir -p /root/sealai/strapi/src/api/product-tab/content-types/product-tab
cat > /root/sealai/strapi/src/api/product-tab/content-types/product-tab/schema.json << 'EOF'
{
  "kind": "collectionType",
  "collectionName": "product_tabs",
  "info": {
    "singularName": "product-tab",
    "pluralName": "product-tabs",
    "displayName": "Product Tab",
    "description": "Tabs for the product section"
  },
  "options": {
    "draftAndPublish": true
  },
  "pluginOptions": {},
  "attributes": {
    "title": {
      "type": "string",
      "required": true
    },
    "image": {
      "type": "media",
      "multiple": false,
      "required": false,
      "allowedTypes": ["images"]
    },
    "accordionItems": {
      "type": "component",
      "repeatable": true,
      "component": "shared.accordion-item"
    },
    "order": {
      "type": "integer",
      "default": 0
    }
  }
}
EOF

# Re-create existing types (Hero, Section, Feature, Next Step, Community) to ensure consistency
# (Skipping full re-creation here to avoid overwriting if not needed, but ensuring directories exist)

echo "New content type schemas created successfully!"

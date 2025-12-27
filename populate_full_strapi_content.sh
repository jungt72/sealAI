#!/bin/bash

# Wait for Strapi to be ready
echo "Waiting for Strapi to be ready..."
sleep 10

# Define API URL
API_URL="http://localhost:1337/api"

# --- Populate Global ---
echo "Populating Global..."
curl -X POST "$API_URL/global" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "siteName": "SealAI",
      "copyrightText": "© 2025 SealAI GmbH. Alle Rechte vorbehalten.",
      "navbarLinks": [
        { "label": "Careers", "href": "#", "isExternal": false },
        { "label": "Investors", "href": "#", "isExternal": false },
        { "label": "Suppliers", "href": "#", "isExternal": false },
        { "label": "Newsroom", "href": "#", "isExternal": false }
      ],
      "sectionNavItems": [
        { "label": "Produkte", "href": "products", "isExternal": false },
        { "label": "Features", "href": "features", "isExternal": false },
        { "label": "Community", "href": "community", "isExternal": false },
        { "label": "Nächste Schritte", "href": "next-steps", "isExternal": false }
      ],
      "footerColumns": [
        {
          "title": "Neuigkeiten",
          "links": [
            { "label": "Features", "href": "#", "isExternal": false },
            { "label": "Sicherheit", "href": "#", "isExternal": false },
            { "label": "Roadmap", "href": "#", "isExternal": false }
          ]
        },
        {
          "title": "Microsoft Store",
          "links": [
            { "label": "Konto-Profil", "href": "#", "isExternal": false },
            { "label": "Download Center", "href": "#", "isExternal": false },
            { "label": "Rückgaben", "href": "#", "isExternal": false }
          ]
        },
        {
          "title": "Bildungswesen",
          "links": [
            { "label": "Microsoft Bildung", "href": "#", "isExternal": false },
            { "label": "Geräte für Bildung", "href": "#", "isExternal": false },
            { "label": "Microsoft Teams", "href": "#", "isExternal": false }
          ]
        },
        {
          "title": "Unternehmen",
          "links": [
            { "label": "Microsoft Cloud", "href": "#", "isExternal": false },
            { "label": "Microsoft Security", "href": "#", "isExternal": false },
            { "label": "Azure", "href": "#", "isExternal": false }
          ]
        }
      ],
      "footerBottomLinks": [
        { "label": "Impressum", "href": "#", "isExternal": false },
        { "label": "Datenschutz", "href": "#", "isExternal": false },
        { "label": "Cookies", "href": "#", "isExternal": false }
      ]
    }
  }'

# --- Populate Product Tabs ---
echo "Populating Product Tabs..."

# Tab 1
curl -X POST "$API_URL/product-tabs" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "title": "Copilot in Power Automate",
      "order": 1,
      "accordionItems": [
        {
          "title": "Optimieren von Workflows mit KI-gestützten Low-Code-Automatisierungstools",
          "description": "Optimieren Sie Geschäftsprozesse ganz einfach und erstellen Sie automatisierte Workflows, indem Sie die Ziele in ihren eigenen Worten beschreiben.",
          "link": "#"
        },
        {
          "title": "Identifizieren von Ineffizienzen in vorhandenen Prozessen",
          "description": "Nutzen Sie Process Mining, um Engpässe zu finden und zu beheben.",
          "link": "#"
        },
        {
          "title": "Automatisieren von Aufgaben mit einem „Show-and-Tell“ - Ansatz",
          "description": "Zeigen Sie dem Copilot, was zu tun ist, und lassen Sie ihn die Arbeit erledigen.",
          "link": "#"
        }
      ]
    }
  }'

# Tab 2
curl -X POST "$API_URL/product-tabs" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "title": "Copilot in Power Apps",
      "order": 2,
      "accordionItems": [
        {
          "title": "Erstellen von Apps durch natürliche Sprache",
          "description": "Beschreiben Sie einfach, was Sie brauchen, und SealAI erstellt die App für Sie.",
          "link": "#"
        }
      ]
    }
  }'

# Tab 3
curl -X POST "$API_URL/product-tabs" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "title": "Copilot in Microsoft Fabric",
      "order": 3,
      "accordionItems": [
        {
          "title": "Datenanalyse vereinfachen",
          "description": "Analysieren Sie große Datenmengen mit KI-Unterstützung.",
          "link": "#"
        }
      ]
    }
  }'

# Tab 4
curl -X POST "$API_URL/product-tabs" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "title": "Copilot in Power Pages",
      "order": 4,
      "accordionItems": [
        {
          "title": "Websites erstellen mit KI",
          "description": "Erstellen Sie professionelle Websites im Handumdrehen.",
          "link": "#"
        }
      ]
    }
  }'

# Tab 5
curl -X POST "$API_URL/product-tabs" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "title": "Microsoft Copilot Studio",
      "order": 5,
      "accordionItems": [
        {
          "title": "Chatbots erstellen",
          "description": "Entwickeln Sie intelligente Chatbots ohne Code.",
          "link": "#"
        }
      ]
    }
  }'

echo "Content population complete!"

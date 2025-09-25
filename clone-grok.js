const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  await page.goto('https://example.com', {
    waitUntil: 'networkidle2',
    timeout: 60000,
  });

  const html = await page.content();

  fs.writeFileSync('example-clone.html', html);

  console.log('✅ example.com erfolgreich gespeichert als example-clone.html');

  await browser.close();
})();

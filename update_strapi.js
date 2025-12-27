async function run() {
    try {
        console.log('Authenticating as Admin...');
        const loginRes = await fetch('http://localhost:1337/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: 'mail@thorsten-jung.de', password: 'Katerkimba!1' })
        });

        if (!loginRes.ok) {
            const errText = await loginRes.text();
            console.error('Admin Login failed:', loginRes.status, errText);
            process.exit(1);
        }

        const loginData = await loginRes.json();
        const token = loginData.data.token;
        console.log('Authenticated as Admin.');

        // Update with only the content fields
        console.log('Updating Hero with typing animation...');
        const updateRes = await fetch('http://localhost:1337/content-manager/single-types/api::hero.hero', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                title: 'sealing intelligence',
                subtitle: 'SealAI ist Ihr digitaler Fachassistent für Dichtungstechnik.\nEr prüft Ihre Betriebsbedingungen, stellt die nötigen, kritischen Rückfragen und bereitet herstellerneutrale, begründete Dichtungsempfehlungen vor.',
                cta_text: 'Mehr erfahren',
                cta_link: '#',
                staticText: 'Building brain interfaces to restore',
                dynamicKeywords: [
                    { text: 'vision' },
                    { text: 'mobility' },
                    { text: 'communication' }
                ]
            })
        });

        if (!updateRes.ok) {
            const errText = await updateRes.text();
            console.error('Update failed:', updateRes.status, errText);
            process.exit(1);
        }

        const updateData = await updateRes.json();
        console.log('Update successful!');

        // Publish the content
        console.log('Publishing...');
        const publishRes = await fetch('http://localhost:1337/content-manager/single-types/api::hero.hero/actions/publish', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({})
        });

        if (!publishRes.ok) {
            const errText = await publishRes.text();
            console.error('Publish failed:', publishRes.status, errText);
            process.exit(1);
        }

        const publishData = await publishRes.json();
        console.log('Published successfully!');
        console.log('Final data:', JSON.stringify(publishData, null, 2));

    } catch (e) {
        console.error('Error:', e);
        process.exit(1);
    }
}
run();

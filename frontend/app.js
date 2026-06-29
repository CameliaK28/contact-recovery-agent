/**
 * Customer Contact Recovery Agent - Frontend Application Logic
 * Updated: Paste-to-parse workflow
 */

const API_URL = '/api/search';
const PARSE_URL = '/api/parse';

// Demo data
const DEMO_TEXT = `Thomas Cater III
Muse Studios
museatlantastaff@gmail.com
+1 404-795-7907
1522 Dekalb Ave NE
Atlanta GA 30307
United States`;

// DOM Elements
const pasteInput = document.getElementById('pasteInput');
const searchBtn = document.getElementById('searchBtn');
const clearBtn = document.getElementById('clearBtn');
const demoBtn = document.getElementById('demoBtn');
const confirmSearchBtn = document.getElementById('confirmSearchBtn');
const editManualBtn = document.getElementById('editManualBtn');
const newSearchBtn = document.getElementById('newSearchBtn');
const retryBtn = document.getElementById('retryBtn');

const inputSection = document.getElementById('inputSection');
const parsedPreview = document.getElementById('parsedPreview');
const manualEntry = document.getElementById('manualEntry');
const progressSection = document.getElementById('progressSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');

// Current parsed data (set after /api/parse)
let currentParsed = null;

// Event Listeners
searchBtn.addEventListener('click', handleParseAndSearch);
clearBtn.addEventListener('click', handleClear);
demoBtn.addEventListener('click', handleDemo);
confirmSearchBtn.addEventListener('click', handleConfirmSearch);
editManualBtn.addEventListener('click', handleEditManual);
newSearchBtn.addEventListener('click', handleNewSearch);
retryBtn.addEventListener('click', handleNewSearch);

// Also allow Ctrl+Enter to trigger search from textarea
pasteInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleParseAndSearch();
    }
});


/**
 * Step 1: Parse the pasted text, then automatically start search
 */
async function handleParseAndSearch(e) {
    if (e) e.preventDefault();

    const rawText = pasteInput.value.trim();
    if (!rawText) {
        alert('Please paste customer information first.');
        pasteInput.focus();
        return;
    }

    // Show progress immediately (parsing step)
    showProgress('Parsing customer information...', 'Extracting structured fields from pasted text');

    try {
        // Step 1: Parse
        const parseResp = await fetch(PARSE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_text: rawText })
        });

        if (!parseResp.ok) {
            const err = await parseResp.json();
            throw new Error(err.detail || 'Parse failed');
        }

        currentParsed = await parseResp.json();

        // Step 2: Show parsed preview briefly, then auto-start search
        showParsedPreview(currentParsed);

        // Auto-start search after a short delay (let user see the parse result)
        setTimeout(() => {
            startSearch(currentParsed);
        }, 800);

    } catch (error) {
        showError(error.message);
    }
}


/**
 * Show parsed preview in the UI
 */
function showParsedPreview(data) {
    // Update confidence badge
    const badge = document.getElementById('parseConfidenceBadge');
    const val = document.getElementById('parseConfidenceValue');
    const conf = data.confidence || 0;
    val.textContent = conf;
    badge.className = 'confidence-badge ' + getConfidenceClass(conf);

    // Build preview fields HTML
    const fields = [
        { label: 'Name', value: data.name },
        { label: 'Company', value: data.company },
        { label: 'Email', value: data.email },
        { label: 'Phone', value: data.phone },
        { label: 'Address', value: data.address },
    ];

    const html = fields.map(f => `
        <div class="preview-field">
            <span class="preview-label">${f.label}</span>
            <span class="preview-value">${f.value || '<span class="missing">— missing</span>'}</span>
        </div>
    `).join('');

    document.getElementById('previewFields').innerHTML = html;

    // Warnings
    const warningsEl = document.getElementById('parseWarnings');
    if (data.warnings && data.warnings.length) {
        warningsEl.innerHTML = data.warnings.map(w => `<div class="warning-msg">⚠️ ${escapeHtml(w)}</div>`).join('');
        warningsEl.classList.remove('hidden');
    } else {
        warningsEl.classList.add('hidden');
    }

    // Show preview, hide paste area
    parsedPreview.classList.remove('hidden');
}


/**
 * Step 2: User confirmed, start the actual search
 */
async function handleConfirmSearch() {
    if (!currentParsed) return;
    startSearch(currentParsed);
}


/**
 * Start the search with parsed (or manually entered) data
 */
async function startSearch(customerData) {
    showProgress('Searching...', 'Starting multi-channel search');

    // Disable buttons
    searchBtn.disabled = true;
    confirmSearchBtn.disabled = true;

    try {
        simulateProgress();

        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: customerData.name || '',
                company: customerData.company || '',
                email: customerData.email || '',
                phone: customerData.phone || '',
                address: customerData.address || '',
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Search failed');
        }

        const result = await response.json();
        showResults(result);

    } catch (error) {
        showError(error.message);
    } finally {
        searchBtn.disabled = false;
        confirmSearchBtn.disabled = false;
    }
}


/**
 * Show manual entry form (with data from parse or empty)
 */
function handleEditManual() {
    // Fill manual fields from currentParsed
    if (currentParsed) {
        document.getElementById('name').value = currentParsed.name || '';
        document.getElementById('company').value = currentParsed.company || '';
        document.getElementById('email').value = currentParsed.email || '';
        document.getElementById('phone').value = currentParsed.phone || '';
        document.getElementById('address').value = currentParsed.address || '';
    }
    manualEntry.classList.remove('hidden');
    parsedPreview.classList.add('hidden');
}


/**
 * Handle manual form search (if user edits manually and submits)
 */
async function handleManualSearch(e) {
    if (e) e.preventDefault();
    const data = {
        name: document.getElementById('name').value.trim(),
        company: document.getElementById('company').value.trim(),
        email: document.getElementById('email').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        address: document.getElementById('address').value.trim(),
    };
    currentParsed = data;
    startSearch(data);
}

// Attach manual form submit
document.getElementById('searchForm').addEventListener('submit', handleManualSearch);


function simulateProgress() {
    const steps = progressSection.querySelectorAll('.step');
    const messages = [
        'Building customer identity profile...',
        'Executing multi-channel search...',
        'Reading web pages and extracting contacts...',
        'Matching entities and calculating confidence...',
        'Deduplicating results...',
        'Formatting output...'
    ];

    steps.forEach(s => { s.classList.remove('active', 'completed'); });

    let currentStep = 0;
    const interval = setInterval(() => {
        if (currentStep < 6) {
            if (currentStep > 0) {
                steps[currentStep - 1].classList.remove('active');
                steps[currentStep - 1].classList.add('completed');
            }
            steps[currentStep].classList.add('active');
            progressMessage.textContent = messages[currentStep];
            currentStep++;
        } else {
            steps[5].classList.remove('active');
            steps[5].classList.add('completed');
            clearInterval(interval);
        }
    }, 3000);

    window._progressInterval = interval;
}


function showProgress(title, message) {
    inputSection.classList.add('hidden');
    parsedPreview.classList.add('hidden');
    manualEntry.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    progressTitle.textContent = title || 'Searching...';
    progressMessage.textContent = message || 'Starting...';
}


function showResults(result) {
    if (window._progressInterval) clearInterval(window._progressInterval);
    progressSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    resultsSection.classList.remove('hidden');

    const confidence = result.match_confidence || 0;
    const badge = document.getElementById('matchConfidenceBadge');
    badge.className = 'confidence-badge ' + getConfidenceClass(confidence);
    document.getElementById('matchConfidenceValue').textContent = confidence + '%';
    document.getElementById('resultName').textContent = result.customer.name || '—';
    document.getElementById('resultCompany').textContent = result.customer.company || '—';

    renderProvidedContacts(result.customer || {});
    renderContacts('confirmedContacts', result.confirmed_contacts || [], 'confirmed');
    const providedCount = countProvided(result.customer || {});
    document.getElementById('confirmedCount').textContent = providedCount + (result.confirmed_contacts || []).length;

    renderContacts('potentialContacts', result.potential_contacts || [], 'potential');
    document.getElementById('potentialCount').textContent = (result.potential_contacts || []).length;

    renderSocialProfiles('socialProfiles', result.social_media_profiles || []);
    document.getElementById('socialCount').textContent = (result.social_media_profiles || []).length;

    renderSources('sourcesList', result.sources || []);
    document.getElementById('sourcesCount').textContent = (result.sources || []).length;

    renderMetadata('metadataGrid', result.metadata || {});

    // Show map when no direct contacts or social profiles found
    checkAndShowMap(result);
}


function showError(message) {
    if (window._progressInterval) clearInterval(window._progressInterval);
    progressSection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    inputSection.classList.add('hidden');
    errorSection.classList.remove('hidden');
    document.getElementById('errorMessage').textContent = message;
}


function handleClear() {
    pasteInput.value = '';
    currentParsed = null;
    parsedPreview.classList.add('hidden');
    manualEntry.classList.add('hidden');
    pasteInput.focus();
}


function handleDemo() {
    pasteInput.value = DEMO_TEXT;
    pasteInput.focus();
}


function handleNewSearch() {
    resultsSection.classList.add('hidden');
    errorSection.classList.add('hidden');
    progressSection.classList.add('hidden');
    parsedPreview.classList.add('hidden');
    manualEntry.classList.add('hidden');
    inputSection.classList.remove('hidden');
    currentParsed = null;
    pasteInput.value = '';
    pasteInput.focus();
}


// ------- Render helpers -------


/**
 * Always show the map for the customer's address when available.
 * Map is now a permanent fixture in the results.
 */
function checkAndShowMap(result) {
    const address = result.customer && result.customer.original_address;
    const mapCard = document.getElementById('mapCard');

    if (address) {
        showMap(address);
    } else {
        mapCard.classList.add('hidden');
    }
}


/**
 * Geocode an address via OpenStreetMap Nominatim API (free, no API key)
 * and display an embedded OpenStreetMap with a marker.
 */
async function showMap(address) {
    const mapCard = document.getElementById('mapCard');
    const mapContainer = document.getElementById('mapContainer');
    const mapAddress = document.getElementById('mapAddress');

    mapCard.classList.remove('hidden');
    mapContainer.innerHTML = '<div class="map-loading">Locating address...</div>';
    mapAddress.textContent = '';

    try {
        const q = encodeURIComponent(address);
        const resp = await fetch(
            `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&addressdetails=1`,
            { headers: { 'Accept-Language': 'en' } }
        );

        if (!resp.ok) throw new Error('Geocoding request failed');

        const data = await resp.json();

        if (data && data.length > 0) {
            const lat = parseFloat(data[0].lat);
            const lon = parseFloat(data[0].lon);
            const displayName = data[0].display_name || address;
            const delta = 0.008; // zoom level
            const minLon = lon - delta, maxLon = lon + delta;
            const minLat = lat - delta, maxLat = lat + delta;

            mapContainer.innerHTML = `
                <iframe
                    width="100%"
                    height="350"
                    frameborder="0"
                    scrolling="no"
                    marginheight="0"
                    marginwidth="0"
                    src="https://www.openstreetmap.org/export/embed.html?bbox=${minLon}%2C${minLat}%2C${maxLon}%2C${maxLat}&layer=mapnik&marker=${lat}%2C${lon}"
                    style="border: 0;">
                </iframe>
            `;

            const osmLink = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}`;
            const gmapsLink = `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`;
            mapAddress.innerHTML = `
                <span class="map-label">Address:</span> ${escapeHtml(displayName)}
                <br>
                <a href="${osmLink}" target="_blank" class="map-link">OpenStreetMap ↗</a>
                <a href="${gmapsLink}" target="_blank" class="map-link">Google Maps ↗</a>
            `;
        } else {
            // Fallback: try Google Maps embed without geocoding
            mapContainer.innerHTML = `
                <iframe
                    width="100%"
                    height="350"
                    frameborder="0"
                    scrolling="no"
                    marginheight="0"
                    marginwidth="0"
                    src="https://www.google.com/maps?q=${q}&output=embed"
                    style="border: 0;">
                </iframe>
            `;
            mapAddress.innerHTML = `<span class="map-label">Address:</span> ${escapeHtml(address)}`;
        }
    } catch (e) {
        // Fallback: try Google Maps embed
        try {
            const q = encodeURIComponent(address);
            mapContainer.innerHTML = `
                <iframe
                    width="100%"
                    height="350"
                    frameborder="0"
                    scrolling="no"
                    marginheight="0"
                    marginwidth="0"
                    src="https://www.google.com/maps?q=${q}&output=embed"
                    style="border: 0;">
                </iframe>
            `;
            mapAddress.innerHTML = `<span class="map-label">Address:</span> ${escapeHtml(address)}`;
        } catch {
            mapContainer.innerHTML = '<div class="map-loading">Could not load map for this address</div>';
            mapAddress.textContent = address;
        }
    }
}


// SVG icons for provided contact types
const PROVIDED_TYPE_ICONS = {
    name: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    company: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>',
    email: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
    phone: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    address: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
};


/**
 * Render the customer's original input information in the Provided section.
 * This shows what the user already knows, for easy review.
 */
function renderProvidedContacts(customer) {
    const container = document.getElementById('providedContacts');
    const items = [];

    if (customer.name) {
        items.push({
            type: 'name', label: 'Name', value: customer.name,
            valueHtml: escapeHtml(customer.name), iconClass: 'name-icon'
        });
    }
    if (customer.company) {
        items.push({
            type: 'company', label: 'Company', value: customer.company,
            valueHtml: escapeHtml(customer.company), iconClass: 'company-icon'
        });
    }
    if (customer.original_email) {
        items.push({
            type: 'email', label: 'Email', value: customer.original_email,
            valueHtml: `<a href="mailto:${customer.original_email}">${escapeHtml(customer.original_email)}</a>`,
            iconClass: 'email-icon'
        });
    }
    if (customer.original_phone) {
        items.push({
            type: 'phone', label: 'Phone', value: customer.original_phone,
            valueHtml: `<a href="tel:${customer.original_phone}">${escapeHtml(customer.original_phone)}</a>`,
            iconClass: 'phone-icon'
        });
    }
    if (customer.original_address) {
        items.push({
            type: 'address', label: 'Address', value: customer.original_address,
            valueHtml: escapeHtml(customer.original_address), iconClass: 'address-icon'
        });
    }

    if (items.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div class="provided-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            Provided Information
        </div>
        ${items.map(item => `
            <div class="provided-item">
                <div class="provided-type-icon ${item.iconClass}">
                    ${PROVIDED_TYPE_ICONS[item.type]}
                </div>
                <div>
                    <div class="provided-label">${item.label}</div>
                    <div class="provided-value">${item.valueHtml}</div>
                </div>
                <span class="provided-badge">Provided</span>
            </div>
        `).join('')}
    `;
}


/**
 * Count how many provided fields have values.
 */
function countProvided(customer) {
    let count = 0;
    if (customer.name) count++;
    if (customer.company) count++;
    if (customer.original_email) count++;
    if (customer.original_phone) count++;
    if (customer.original_address) count++;
    return count;
}


function renderContacts(containerId, contacts, category) {
    const container = document.getElementById(containerId);
    if (!contacts.length) {
        container.innerHTML = '<p class="empty-msg">No contacts found in this category</p>';
        return;
    }
    container.innerHTML = contacts.map((contact, i) => {
        const typeLabel = getTypeLabel(contact.type);
        const confidenceClass = getConfidenceClass(contact.confidence);
        const valueHtml = formatContactValue(contact);
        const factorsHtml = formatMatchFactors(contact.match_factors, contact.mismatch_factors);
        return `
            <div class="contact-item" style="animation-delay: ${i * 0.05}s">
                <div class="contact-item-header">
                    <span class="contact-type-badge ${contact.type}">${typeLabel}</span>
                    <span class="contact-confidence ${confidenceClass}">${contact.confidence}%</span>
                </div>
                <div class="contact-value">${valueHtml}</div>
                <div class="contact-source">Source: <a href="${contact.source_url}" target="_blank">${truncateUrl(contact.source_url)}</a></div>
                <div class="contact-evidence" title="Click to expand">${escapeHtml(contact.evidence || 'No evidence text available')}</div>
                ${factorsHtml ? `<div class="match-factors">${factorsHtml}</div>` : ''}
            </div>
        `;
    }).join('');
}


function renderSources(containerId, sources) {
    const container = document.getElementById(containerId);
    if (!sources.length) {
        container.innerHTML = '<p class="empty-msg">No sources recorded</p>';
        return;
    }
    container.innerHTML = sources.map(source => {
        const statusClass = source.fetched ? 'fetched' : 'failed';
        const channelLabel = getChannelLabel(source.channel);
        return `
            <div class="source-item">
                <span class="source-status ${statusClass}"></span>
                <span class="source-channel">${channelLabel}</span>
                <span class="source-url"><a href="${source.url}" target="_blank">${truncateUrl(source.url)}</a></span>
                <span class="source-count">${source.contacts_found || 0} contacts</span>
            </div>
        `;
    }).join('');
}


function renderMetadata(containerId, metadata) {
    const container = document.getElementById(containerId);
    const items = [
        { label: 'Search Queries', value: metadata.queries_used || 0 },
        { label: 'URLs Found', value: metadata.urls_searched || 0 },
        { label: 'Pages Read', value: metadata.urls_fetched || 0 },
        { label: 'Contacts Extracted', value: metadata.contacts_extracted || 0 },
        { label: 'After Dedup', value: metadata.contacts_after_dedup || 0 },
        { label: 'Time (seconds)', value: metadata.elapsed_seconds || 0 },
    ];
    container.innerHTML = items.map(item => `
        <div class="metadata-item">
            <span class="meta-label">${item.label}</span>
            <span class="meta-value">${item.value}</span>
        </div>
    `).join('');
}


// Social media platform SVG icons
const SOCIAL_ICONS = {
    facebook: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>',
    instagram: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.949.149-3.227 1.664-4.771 4.979-4.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>',
    linkedin: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    twitter: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    youtube: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
    tiktok: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>',
};


function renderSocialProfiles(containerId, profiles) {
    const container = document.getElementById(containerId);
    if (!profiles.length) {
        container.innerHTML = '<p class="empty-msg">No social media profiles found</p>';
        return;
    }
    container.innerHTML = profiles.map((profile, i) => {
        const platform = profile.type.replace('_profile', '');
        const icon = SOCIAL_ICONS[platform] || '';
        const confidenceClass = getConfidenceClass(profile.confidence);
        const factorsHtml = formatMatchFactors(profile.match_factors, profile.mismatch_factors);
        const handle = extractSocialHandle(profile.value, platform);
        // Show cross-verification badge if available
        const crossVerified = profile.cross_verified;
        const crossPlatforms = profile.cross_verified_platforms || [];
        const crossBadge = crossVerified ? `
            <span class="cross-verified-badge" title="Same handle found on ${crossPlatforms.join(', ')}">
                ✓ Cross-verified on ${crossPlatforms.join(', ')}
            </span>
        ` : '';
        // Show secondary search badge
        const secondaryBadge = profile.secondary_search ? `
            <span class="secondary-search-badge">🔄 Secondary search</span>
        ` : '';
        return `
            <div class="social-item">
                <div class="social-item-main">
                    <div class="social-platform-icon ${platform}">${icon}</div>
                    <div class="social-info">
                        <div class="social-platform-name">${getTypeLabel(profile.type)}</div>
                        <a href="${profile.value}" target="_blank" class="social-link">${handle}</a>
                        ${crossBadge}${secondaryBadge}
                    </div>
                    <span class="contact-confidence ${confidenceClass}">${profile.confidence}%</span>
                </div>
                <div class="contact-source">Found on: <a href="${profile.source_url}" target="_blank">${truncateUrl(profile.source_url)}</a></div>
                ${factorsHtml ? `<div class="match-factors">${factorsHtml}</div>` : ''}
            </div>
        `;
    }).join('');
}


function extractSocialHandle(url, platform) {
    try {
        const u = new URL(url);
        const path = u.pathname.replace(/^\/+/, '').replace(/\/+$/, '');
        if (platform === 'linkedin') return 'linkedin.com/' + path;
        if (platform === 'youtube') return 'youtube.com/' + path;
        return path || url;
    } catch { return url; }
}


// ------- Helpers -------


function getTypeLabel(type) {
    const labels = {
        'phone': 'Phone', 'email': 'Email', 'whatsapp': 'WhatsApp',
        'messenger': 'Messenger', 'contact_form': 'Contact Form',
        'mobile': 'Mobile', 'toll_free': 'Toll Free', 'fax': 'Fax',
        'facebook_profile': 'Facebook', 'instagram_profile': 'Instagram',
        'linkedin_profile': 'LinkedIn', 'twitter_profile': 'Twitter/X',
        'youtube_profile': 'YouTube', 'tiktok_profile': 'TikTok',
    };
    return labels[type] || type;
}


function getConfidenceClass(confidence) {
    if (confidence >= 80) return 'high';
    if (confidence >= 50) return 'medium';
    return 'low';
}


function getChannelLabel(channel) {
    const labels = {
        'official_website': 'Website', 'google_maps': 'Maps', 'social_media': 'Social',
        'business_directory': 'Directory', 'person_search': 'Person', 'email_domain': 'Domain',
        'address_search': 'Address', 'email_username': 'Email Handle',
        'cross_platform_search': 'Cross-platform', 'phone_search': 'Phone',
    };
    return labels[channel] || channel;
}


function formatContactValue(contact) {
    const type = contact.type, value = contact.value;
    if (type === 'email') return `<a href="mailto:${value}">${value}</a>`;
    if (['phone','mobile','whatsapp','toll_free'].includes(type)) return `<a href="tel:${value}">${value}</a>`;
    if (type === 'contact_form') return `<a href="${value}" target="_blank">${truncateUrl(value)}</a>`;
    if (type.includes('profile')) return `<a href="${value}" target="_blank">${value}</a>`;
    return value;
}


function formatMatchFactors(matchFactors, mismatchFactors) {
    let html = '';
    if (matchFactors && matchFactors.length) {
        html += matchFactors.map(f => `<span class="match-factor">${escapeHtml(f)}</span>`).join('');
    }
    if (mismatchFactors && mismatchFactors.length) {
        html += mismatchFactors.map(f => `<span class="mismatch-factor">${escapeHtml(f)}</span>`).join('');
    }
    return html;
}


function truncateUrl(url) {
    if (!url) return '';
    return url.length > 60 ? url.substring(0, 57) + '...' : url;
}


function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

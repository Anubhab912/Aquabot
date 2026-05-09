const $ = id => document.getElementById(id);
let map, marker;

const WMO_ICONS = {
  0:'sun',1:'cloud-sun',2:'cloud',3:'cloudy',
  45:'cloud-fog',48:'cloud-fog',
  51:'cloud-drizzle',53:'cloud-drizzle',55:'cloud-rain',56:'cloud-snow',57:'cloud-snow',
  61:'cloud-rain',63:'cloud-rain',65:'cloud-rain',66:'cloud-snow',67:'cloud-snow',
  71:'snowflake',73:'snowflake',75:'snowflake',77:'cloud-snow',
  80:'cloud-rain',81:'cloud-rain',82:'cloud-lightning',
  85:'cloud-snow',86:'cloud-snow',
  95:'cloud-lightning',96:'cloud-lightning',99:'cloud-lightning',
};

function wmoIcon(code) {
  return WMO_ICONS[code] ?? 'thermometer';
}

function shortDay(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short' });
}

function getCurrentTime() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function showError(msg) {
  const el = $('errorMsg');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function clearError() {
  $('errorMsg').classList.add('hidden');
}

// ─── 3-D Tilt on Mouse Move ─────────────────────────────────────
function attachTilt(card) {
  card.addEventListener('mousemove', e => {
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width  - 0.5;
    const y = (e.clientY - r.top)  / r.height - 0.5;
    card.style.transform = `perspective(800px) rotateY(${x * 10}deg) rotateX(${-y * 10}deg) scale(1.02)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
}

// ─── Render Functions ────────────────────────────────────────────
function renderWeather(ctx) {
  $('cityName').textContent    = `${ctx.city}`;
  $('weatherDesc').textContent = `${ctx.weather_description} · ${ctx.season}`;
  const lastUpdated = $('lastUpdated');
  if (lastUpdated) lastUpdated.textContent = `Last updated: ${getCurrentTime()}`;
  
  $('weatherIcon').innerHTML   = `<i data-lucide="${wmoIcon(ctx.weather_code ?? 0)}"></i>`;
  $('tempMain').textContent    = `${ctx.temperature_c}°C`;
  $('feelsLike').textContent   = `Feels like ${ctx.feels_like_c}°C`;
  $('humidity').textContent    = `${ctx.humidity_pct}%`;
  $('wind').textContent        = `${ctx.wind_kmh} km/h`;
  $('uv').textContent          = ctx.uv_index;
  $('rain').textContent        = `${ctx.precipitation_mm} mm`;

  // Dynamic background tint based on condition category
  const tints = {
    heat_advisory:  'radial-gradient(ellipse at top, rgba(251,191,36,0.08) 0%, transparent 70%)',
    rain_advisory:  'radial-gradient(ellipse at top, rgba(79,142,247,0.10) 0%, transparent 70%)',
    storm_warning:  'radial-gradient(ellipse at top, rgba(139,92,246,0.10) 0%, transparent 70%)',
    cold_advisory:  'radial-gradient(ellipse at top, rgba(96,165,250,0.08) 0%, transparent 70%)',
    clear_day:      'radial-gradient(ellipse at top, rgba(52,211,153,0.08) 0%, transparent 70%)',
    general:        '',
  };
  document.body.style.backgroundImage = tints[ctx.tip_category] || '';
}

function renderForecast(days) {
  const strip = $('forecastStrip');
  strip.innerHTML = days.map(d => `
    <div class="forecast-day">
      <span class="fc-day-label">${shortDay(d.date)}</span>
      <i data-lucide="${descToIcon(d.description)}" class="fc-icon"></i>
      <div class="fc-temps">
        <span class="fc-max">${Math.round(d.temp_max)}°</span>
        <span class="fc-min">${Math.round(d.temp_min)}°</span>
      </div>
      <span class="fc-rain"><i data-lucide="droplet" class="inline-icon-small"></i>${d.precipitation_sum}mm</span>
    </div>
  `).join('');
}

function descToIcon(desc) {
  const d = desc.toLowerCase();
  if (d.includes('thunder'))  return 'cloud-lightning';
  if (d.includes('snow'))     return 'snowflake';
  if (d.includes('rain') || d.includes('drizzle')) return 'cloud-rain';
  if (d.includes('fog'))      return 'cloud-fog';
  if (d.includes('overcast')) return 'cloudy';
  if (d.includes('cloudy'))   return 'cloud';
  if (d.includes('clear'))    return 'sun';
  return 'cloud-sun';
}

function renderInsights(insights) {
  $('aiSummary').textContent = insights.summary;

  const farmList = $('farmingTips');
  farmList.innerHTML = '';
  insights.farming_tips.forEach(t => {
    const li = document.createElement('li');
    li.textContent = t;
    farmList.appendChild(li);
  });

  const healthList = $('healthTips');
  healthList.innerHTML = '';
  insights.health_tips.forEach(t => {
    const li = document.createElement('li');
    li.textContent = t;
    healthList.appendChild(li);
  });

  // Alert banner
  const banner = $('alertBanner');
  if (insights.alert) {
    banner.innerHTML = `<i data-lucide="alert-triangle" class="inline-icon"></i> <span>${insights.alert}</span>`;
    banner.className = `alert-banner ${insights.alert_level}`;
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }
}

function updateMap(lat, lon, fly = true) {
  if (!map) return;
  if (fly) {
    map.flyTo([lat, lon], 10, { duration: 2, easeLinearity: 0.25 });
  }
  if (marker) marker.setLatLng([lat, lon]);
  else marker = L.marker([lat, lon]).addTo(map);
}

// ─── Reverse Geocoding ───────────────────────────────────────────
async function reverseGeocode(lat, lon) {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10`;
    const resp = await fetch(url);
    const data = await resp.json();
    const a = data.address;
    // Prioritize specific landmarks/POI names
    const poi = a.amenity || a.building || a.tourism || a.historic || a.natural || a.leisure || a.shop || a.railway;
    if (poi) return poi;

    // Prioritize specific city, town, or village names
    const city = a.city || a.town || a.village || a.suburb || a.city_district || a.hamlet;
    if (city) return city;
    
    // Fallback to district or state if no city name is found
    const region = a.state_district || a.county || a.state;
    if (region) return region;
    
    return "Selected Region";
  } catch (e) {
    return "Selected Location";
  }
}

// ─── Main Fetch ──────────────────────────────────────────────────
async function fetchInsights(city, lat, lon) {
  $('skeleton').classList.remove('hidden');
  $('results').classList.add('hidden');
  clearError();

  try {
    const url = `/weather?city=${encodeURIComponent(city)}&lat=${lat}&lon=${lon}`;
    const resp = await fetch(url);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();

    renderWeather(data.context);
    renderForecast(data.context.forecast_7day);
    renderInsights(data.insights);
    updateMap(lat, lon, city !== 'Your Location' && !city.includes('Selected')); // Fly only for searches, not for map clicks or geo

    $('results').classList.remove('hidden');

    // Attach 3D tilt after elements are visible
    document.querySelectorAll('.card-3d').forEach(attachTilt);

    // Re-initialize icons for new content
    lucide.createIcons();

  } catch (e) {
    showError(`⚠️ ${e.message}`);
  } finally {
    $('skeleton').classList.add('hidden');
  }
}

// ─── Geocode → Fetch ─────────────────────────────────────────────
async function handleSearch() {
  const city = $('cityInput').value.trim();
  if (!city) { showError('Please enter a location name.'); return; }

  $('skeleton').classList.remove('hidden');
  $('results').classList.add('hidden');
  clearError();

  try {
    const gr = await fetch(`/geocode?city=${encodeURIComponent(city)}`);
    if (!gr.ok) {
      const e = await gr.json().catch(() => ({}));
      throw new Error(e.detail || 'Location not found.');
    }
    const geo = await gr.json();
    $('cityInput').value = geo.city;
    await fetchInsights(geo.city, geo.latitude, geo.longitude);
  } catch (e) {
    $('skeleton').classList.add('hidden');
    showError(`⚠️ ${e.message}`);
  }
}

// ─── Geolocation ─────────────────────────────────────────────────
function handleGeo() {
  if (!navigator.geolocation) {
    showError('Geolocation not supported by your browser.');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    pos => {
      const { latitude: lat, longitude: lon } = pos.coords;
      fetchInsights('Your Location', lat, lon);
    },
    () => showError('Location access denied. Please type a location name.')
  );
}

// ─── Event Listeners ─────────────────────────────────────────────
$('searchBtn').addEventListener('click', handleSearch);
$('geoBtn').addEventListener('click', handleGeo);
$('cityInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') handleSearch();
});

// ─── App Initialization & Splash Screen ───────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initialize any static icons immediately
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
  
  // Cinematic Splash Screen logic
  const splash = $('splashScreen');
  if (splash) {
    setTimeout(() => {
      splash.classList.add('splash-hidden');
      setTimeout(() => splash.remove(), 1000);
      const main = $('mainContainer');
      if (main) main.classList.add('container-enter');
    }, 2800); // Play splash for 2.8s
  } else {
    const main = $('mainContainer');
    if (main) main.classList.add('container-enter');
  }

  // Initialize Background Map
  map = L.map('map', { zoomControl: true, attributionControl: false }).setView([20, 0], 2);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(map);

  // Map Click Interaction
  map.on('click', async e => {
    const { lat, lng } = e.latlng;
    const name = await reverseGeocode(lat, lng);
    $('cityInput').value = name;
    fetchInsights(name, lat, lng);
  });
});

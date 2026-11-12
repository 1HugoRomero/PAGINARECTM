/* Mapa base de AgroAsesor: Google Maps (Maps JavaScript API) debajo de las herramientas de dibujo.
 *
 * - Con GOOGLE_MAPS_API_KEY configurada, el fondo del mapa (normal y satélite) es Google Maps real.
 *   Leaflet sigue encima solo para dibujar, editar vértices y mostrar predios y potreros (GeoJSON);
 *   no se usa la Drawing Library de Google (retirada).
 * - Sin clave, o si Google rechaza la clave (restricciones, API no habilitada, facturación), se avisa en
 *   pantalla con el motivo y se usa el mapa de respaldo (OpenStreetMap / Esri) para poder seguir trabajando.
 *
 * Uso:  const base = AgroBasemap.create(map, config, { onNotice, onTileError, onTileLoad });  base.select('satellite');
 */
(() => {
  'use strict';
  const ESRI_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const ESRI_ATTRIBUTION = '&copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community';
  const MAX_ZOOM = 19;
  const LOAD_TIMEOUT_MS = 15000;
  const GOOGLE_TYPES = { normal: 'roadmap', satellite: 'hybrid' };
  const authListeners = new Set();
  let authFailed = false;
  let loader = null;

  // Google llama a esta función global cuando la clave no es válida para esta página.
  const previousAuthFailure = window.gm_authFailure;
  window.gm_authFailure = () => {
    authFailed = true;
    authListeners.forEach((listener) => listener());
    if (typeof previousAuthFailure === 'function') previousAuthFailure();
  };

  function loadGoogle(key) {
    if (window.google && window.google.maps && window.google.maps.Map) return Promise.resolve(window.google.maps);
    if (loader) return loader;
    loader = new Promise((resolve, reject) => {
      const callbackName = '__agroGoogleMapsReady';
      const timer = window.setTimeout(() => reject(new Error('timeout')), LOAD_TIMEOUT_MS);
      window[callbackName] = () => {
        window.clearTimeout(timer);
        resolve(window.google.maps);
      };
      const script = document.createElement('script');
      script.src =
        'https://maps.googleapis.com/maps/api/js?key=' +
        encodeURIComponent(key) +
        '&v=weekly&loading=async&language=es&region=CL&callback=' +
        callbackName;
      script.async = true;
      script.onerror = () => {
        window.clearTimeout(timer);
        reject(new Error('network'));
      };
      document.head.appendChild(script);
    });
    return loader;
  }

  function create(map, config, options) {
    const opts = options || {};
    const notice = (message, kind) => {
      if (opts.onNotice) opts.onNotice(message, kind || 'info');
      // Aviso visible sobre el mapa (no se oculta el problema detrás del mapa de respaldo).
      const container = map.getContainer();
      let box = container.querySelector('.map-base-notice');
      if (!box) {
        box = document.createElement('p');
        box.className = 'map-base-notice';
        box.setAttribute('role', 'status');
        container.appendChild(box);
      }
      box.dataset.kind = kind || 'info';
      box.textContent = message;
    };
    const state = { view: 'normal', engine: 'pending', gmap: null, holder: null };
    const tiles = {
      normal: L.tileLayer(config.tile_url, { attribution: config.attribution, maxZoom: MAX_ZOOM, crossOrigin: true }),
      satellite: L.tileLayer(ESRI_URL, { attribution: ESRI_ATTRIBUTION, maxZoom: MAX_ZOOM, crossOrigin: true }),
    };
    Object.keys(tiles).forEach((view) => {
      tiles[view].on('tileerror', () => {
        if (state.engine === 'tiles' && state.view === view && opts.onTileError) opts.onTileError();
      });
      tiles[view].on('tileload', () => {
        if (state.engine === 'tiles' && state.view === view && opts.onTileLoad) opts.onTileLoad();
      });
    });
    map.setMaxZoom(MAX_ZOOM);

    function apply() {
      if (state.engine === 'google') {
        state.gmap.setMapTypeId(GOOGLE_TYPES[state.view]);
        return;
      }
      if (state.engine !== 'tiles') return;
      Object.keys(tiles).forEach((view) => {
        if (view !== state.view && map.hasLayer(tiles[view])) map.removeLayer(tiles[view]);
      });
      if (!map.hasLayer(tiles[state.view])) tiles[state.view].addTo(map);
    }

    function useTiles() {
      if (state.holder) state.holder.remove();
      state.holder = null;
      state.gmap = null;
      state.engine = 'tiles';
      map.getContainer().classList.remove('has-google-base');
      if (map.attributionControl && !map.attributionControl._map) map.attributionControl.addTo(map);
      apply();
    }

    function sync(center, zoom) {
      if (!state.gmap || !center || !Number.isFinite(zoom)) return;
      state.gmap.moveCamera({ center: { lat: center.lat, lng: center.lng }, zoom });
    }

    function syncFromMap() {
      try {
        sync(map.getCenter(), map.getZoom());
      } catch (error) {
        /* el mapa todavía no tiene vista (se ajusta al cargar la geometría) */
      }
    }

    function useGoogle(maps) {
      const holder = document.createElement('div');
      holder.className = 'agro-google-base';
      holder.setAttribute('aria-hidden', 'true');
      map.getContainer().insertBefore(holder, map.getContainer().firstChild);
      state.holder = holder;
      state.gmap = new maps.Map(holder, {
        center: { lat: -33.6866, lng: -71.2167 },
        zoom: 12,
        mapTypeId: GOOGLE_TYPES[state.view],
        disableDefaultUI: true,
        gestureHandling: 'none',
        keyboardShortcuts: false,
        clickableIcons: false,
        isFractionalZoomEnabled: true,
        maxZoom: MAX_ZOOM,
      });
      state.engine = 'google';
      map.getContainer().classList.add('has-google-base');
      // La atribución la muestra Google en su propia capa.
      if (map.attributionControl) map.attributionControl.remove();
      map.on('move zoom zoomend moveend resize viewreset', syncFromMap);
      map.on('zoomanim', (event) => sync(event.center, event.zoom));
      syncFromMap();
      apply();
    }

    function googleRejected() {
      if (state.engine === 'tiles') return;
      useTiles();
      notice(
        'Google Maps rechazó la clave de API. Revisa en Google Cloud que «Maps JavaScript API» esté habilitada, ' +
          'que la facturación esté activa y que la clave permita este sitio (' +
          window.location.origin +
          '). Mientras tanto se muestra el mapa de respaldo (OpenStreetMap).',
        'error',
      );
    }

    if (!config.google_maps_key) {
      useTiles();
      if (config.debug) {
        notice(
          'Google Maps no está configurado: falta GOOGLE_MAPS_API_KEY en el archivo .env. ' +
            'Se muestra el mapa de respaldo (OpenStreetMap).',
          'warning',
        );
      }
    } else if (authFailed) {
      googleRejected();
    } else {
      authListeners.add(googleRejected);
      loadGoogle(config.google_maps_key)
        .then((maps) => {
          if (authFailed) return;
          useGoogle(maps);
        })
        .catch((error) => {
          useTiles();
          notice(
            (error && error.message === 'timeout'
              ? 'Google Maps tardó demasiado en responder.'
              : 'No se pudo descargar Google Maps (revisa la conexión a internet).') +
              ' Se muestra el mapa de respaldo (OpenStreetMap).',
            'error',
          );
        });
    }

    return {
      select(view) {
        state.view = view === 'satellite' ? 'satellite' : 'normal';
        apply();
      },
      get view() {
        return state.view;
      },
      get engine() {
        return state.engine;
      },
    };
  }

  window.AgroBasemap = { create };
})();

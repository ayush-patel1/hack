import axios from 'axios';

const API = axios.create({ baseURL: '/api' });

// Data endpoints
export const fetchSummary = () => API.get('/data/summary').then(r => r.data);
export const fetchViolations = () => API.get('/data/violations').then(r => r.data);
export const fetchReference = () => API.get('/data/reference').then(r => r.data);
export const fetchCurrent = () => API.get('/data/current').then(r => r.data);
export const fetchMetadata = () => API.get('/data/metadata').then(r => r.data);
export const fetchSatelliteChanges = () => API.get('/data/satellite-changes').then(r => r.data);
export const fetchCsidcPlots = () => API.get('/data/csidc-plots').then(r => r.data);
export const fetchLivePlots = () => API.get('/data/live-plots').then(r => r.data);
export const fetchLiveBoundaries = () => API.get('/data/live-boundaries').then(r => r.data);
export const fetchAnalysisResults = () => API.get('/data/analysis-results').then(r => r.data);

// Analysis endpoints
export const runAnalysis = () => API.post('/analysis/run').then(r => r.data);
export const generateReport = (data) => API.post('/analysis/generate-report', data || {}, { responseType: 'blob' });
export const generateComplianceReport = () => API.post('/analysis/compliance-report', {}, { responseType: 'blob' });

// CSIDC endpoints
export const listCsidcAreas = () => API.get('/csidc/areas').then(r => r.data);
export const fetchCsidcLive = (area, maxPlots = 500) =>
  API.post('/csidc/fetch', { area, max_plots: maxPlots }).then(r => r.data);

// Export endpoints
export const exportCSV = () => API.get('/export/csv', { responseType: 'blob' });
export const exportGeoJSON = () => API.get('/export/geojson', { responseType: 'blob' });

// Pipeline
export const generateSampleData = () => API.post('/pipeline/generate-data').then(r => r.data);

// Image helpers
export const getPlotImageUrl = (plotId, type) => `/api/images/${plotId}/${type}`;
export const getChangeMaskUrl = (filename) => `/api/images/change-mask/${filename}`;
export const fetchChangeMasks = () => API.get('/images/change-masks').then(r => r.data);

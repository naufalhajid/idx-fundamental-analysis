import { apiGet } from '$lib/clients/httpClient';
import type { HealthResponse } from '$lib/types/api';

export async function getHealth(): Promise<HealthResponse> {
	return apiGet<HealthResponse>('/api/v1/health');
}

import { API_BASE_URL } from '$lib/config/api';

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
	const url = new URL(path, API_BASE_URL).toString();

	const response = await fetch(url, {
		method: 'GET',
		// Allow overriding or extending options if needed
		...init
	});

	if (!response.ok) {
		throw new Error(`Request failed with status ${response.status}`);
	}

	return (await response.json()) as T;
}

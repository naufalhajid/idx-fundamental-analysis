import { env } from '$env/dynamic/public';

export const API_BASE_URL = env.PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

import { getHealth } from '$lib/services/healthService';

export const load = async () => {
	const health = await getHealth();

	return { health };
};

<script lang="ts">
	import type { HealthResponse } from '$lib/types/api';

	let { data } = $props<{ data: { health: HealthResponse } }>();

	const status = $derived(data.health.status);
</script>

<main>
	<h1>IDX Fundamental UI</h1>
	<p>Backend health: {status}</p>
</main>

import { initializeLiveMapObservation } from './live_observation.js';
import { initializeGlobalMapObservation } from './global_observation.js';

// Share lifecycle events only. Global jobs never receive a scene or a live
// model, and never request the continuous cloud/pose transport.
export function initializeSavedMapObservations(options) {
  const live = initializeLiveMapObservation(options);
  const global = initializeGlobalMapObservation({ getContext: options.getContext });
  return {
    wanted: () => live?.wanted() || false,
    render: changed => { global?.render(); return live?.render(changed) || false; },
    ingestPose: value => live?.ingestPose(value),
    ingestCloud: value => { global?.ingestCloud(value); return live?.ingestCloud(value); },
    reset: reason => { global?.reset(reason); live?.reset(reason); },
    destroy: () => { global?.destroy(); live?.destroy(); },
  };
}

# Editorial source notes — human anatomy batch

This is a scoped editorial review, not a blanket certification of every quantity
or anatomical detail in generated illustrations. The current source of carousel
copy is `BATCH_CONFIG` in `build_carousel_batch.py`.

## Post 01: Human Eye (`01-human-eye`)
- **Hook**: "How Your Eyes Turn Light Into Vision"
- Removed unsupported zero-lag, photon-throughput, and visual-cortex percentage claims.
- Cornea/lens focusing and cone-rich central vision remain the educational focus.
- Background reference: [OpenStax sensory perception](https://openstax.org/books/anatomy-and-physiology-2e/pages/14-1-sensory-perception).
- Remaining numerical cell-count and optical-power statements were not independently
  remeasured in this software audit; do not treat the old blanket 'Verified' labels as evidence.

## Post 02: Human Heart (`02-human-heart`)
- **Hook**: "The Unstoppable Hydraulic Pump in Your Chest"
- Corrected the claim that all four valves shut against 120 mmHg. Valve motion
  follows changing pressure differences; atrioventricular and semilunar valves
  operate at different phases of the cardiac cycle.
- Reviewed source: [OpenStax cardiac cycle](https://openstax.org/books/anatomy-and-physiology-2e/pages/19-3-cardiac-cycle).
- Other circulation quantities remain approximate educational values.

## Post 03: Human Brain (`03-human-brain`)
- **Hook**: "The 86-Billion-Neuron Bioelectric Supercomputer"
- Corrected synaptic transport: vesicles fuse with the presynaptic membrane;
  released neurotransmitter molecules cross the cleft and bind receptors.
- Reviewed source: [OpenStax neural communication](https://openstax.org/books/introduction-behavioral-neuroscience/pages/2-1-neural-communication).
- Numerical connectome and capillary-length estimates were not comprehensively
  revalidated. AI illustrations do not establish microscopic scale or accuracy.

## Post 04: Human Lungs (`04-human-lungs`)
- **Hook**: "The Microscopic Air Sacs Keeping You Breathing"
- Removed the incorrect equation of 70–100 square meters with a full tennis court.
- Educational focus: numerous alveoli provide a large surface; the thin respiratory
  membrane enables diffusion; type II cells supply surfactant that lowers surface tension.
- Reviewed source: [OpenStax respiratory system](https://openstax.org/books/fundamentals-nursing/pages/19-1-respiratory-system).

All posts retain an AI illustration disclosure. Clinical interpretation and a
complete scientific review are outside this automation audit.

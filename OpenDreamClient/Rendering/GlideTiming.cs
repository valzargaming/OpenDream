namespace OpenDreamClient.Rendering;

/// <summary>Movement cadence controls automatic gliding; explicit glide sizes keep their configured speed.</summary>
public static class GlideTiming {
    public static float Speed(int iconSize, float glideSize, float tickRate, float automaticSpeed) =>
        glideSize == 0 ? automaticSpeed : glideSize / iconSize * tickRate;

    public static float AutomaticSpeed(int iconSize, float tickRate, float remaining, float elapsed) {
        var baseline = 4f / iconSize * tickRate;
        // A repeated step must cover the remaining rendered distance within the observed interval.
        // Same-tick updates use one tick, avoiding division by zero or an unbounded speed.
        var interval = Math.Max(elapsed, 1f / tickRate);
        return elapsed >= 0 ? Math.Max(baseline, remaining / interval) : baseline;
    }
}

using System;
using System.Globalization;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamShared;

namespace Content.IntegrationTests;

[TestFixture]
[NonParallelizable]
[Explicit("Requires a separate test host because BYOND API initialization is process-global")]
public sealed class WorldRealtimeClockTests : ContentIntegrationTest {
    private static readonly DateTime Epoch = new(2000, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    [Test]
    public async Task UtcEpochDeciseconds() {
        var originalDirectory = Directory.GetCurrentDirectory();
        var temporary = Path.Combine(Path.GetTempPath(), "opendream-realtime-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try {
            var fixture = Path.Combine(temporary, "fixture.dm");
            File.Copy(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "DMProject", "Fixtures", "world-realtime-clock.dm"), fixture);
            var compiler = new DMCompiler.DMCompiler();
            var compiled = compiler.Compile(new() { Files = [fixture], StoreMessages = true });
            var json = Path.ChangeExtension(fixture, "json");
            Assert.That(compiled && File.Exists(json), Is.True,
                "Isolated clock DM fixture compilation failed: " + string.Join("\n", compiler.CompilerMessages));
            var options = new ServerContentIntegrationOption();
            options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = json;
            var server = StartServer(options);
            await server.WaitIdleAsync();
            await server.WaitRunTicks(1);
            Assert.That(server.IsAlive, Is.True);
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                var tree = server.ResolveDependency<DreamObjectTree>();
                Assert.That(manager.LastDMException, Is.Null, "Isolated clock server boot");
                Assert.That(tree.TryGetGlobalProc("world_realtime_clock_probe", out var proc), Is.True);
                Assert.That(tree.TryGetGlobalProc("world_timeofday_clock_probe", out var timeofdayProc), Is.True);
                AssertTimeOfDaySmoke(() => manager.WorldInstance.GetVariable("timeofday"),
                    () => DreamThread.Run(timeofdayProc!, manager.WorldInstance, null));
                Assert.Multiple(() => {
                    AssertRealtimeSample("PUBLIC", () => manager.WorldInstance.GetVariable("realtime"));
                    AssertRealtimeSample("COMPILED", () => DreamThread.Run(proc!, manager.WorldInstance, null));
                });
                Assert.That(manager.LastDMException, Is.Null);
                TestContext.Out.WriteLine("WORLD_REALTIME_COMPLETE: public and compiled UTC epoch bounds with float precision");
            });
        } finally {
            // Loading the compiled fixture changes the process working directory.
            Directory.SetCurrentDirectory(originalDirectory);
            Directory.Delete(temporary, recursive: true);
        }
    }

    private static (float Actual, int Lower, int Upper) ReadTimeOfDay(Func<DreamValue> getter) {
        var before = DateTime.UtcNow;
        using var value = getter();
        var after = DateTime.UtcNow;
        return (value.MustGetValueAsFloat(), (int)(before.TimeOfDay.TotalMilliseconds / 100),
            (int)(after.TimeOfDay.TotalMilliseconds / 100));
    }

    private static bool InDayBracket(float actual, int lower, int upper) =>
        lower <= upper ? actual >= lower && actual <= upper : actual >= lower || actual <= upper;

    private static void AssertTimeOfDaySmoke(Func<DreamValue> publicGetter, Func<DreamValue> compiledGetter) {
        var utcStart = DateTime.UtcNow;
        var watch = Stopwatch.StartNew();
        var publicBefore = ReadTimeOfDay(publicGetter);
        var compiledBefore = ReadTimeOfDay(compiledGetter);
        Thread.Sleep(1200);
        var publicAfter = ReadTimeOfDay(publicGetter);
        var compiledAfter = ReadTimeOfDay(compiledGetter);
        watch.Stop();
        var utcElapsed = (DateTime.UtcNow - utcStart).TotalMilliseconds / 100;
        var stopwatchElapsed = watch.Elapsed.TotalMilliseconds / 100;
        Assert.That(stopwatchElapsed, Is.GreaterThanOrEqualTo(11.5), "TIMEOFDAY_HOST_DELAY");
        Assert.That(stopwatchElapsed, Is.LessThan(864000), "TIMEOFDAY_HOST_DELAY_UNDER_ONE_DAY");
        Assert.That(utcElapsed >= 11.5 && utcElapsed < 864000 && Math.Abs(stopwatchElapsed - utcElapsed) <= 5,
            Is.True, "TIMEOFDAY_HOST_CLOCK_BRACKET_SUPPORTED");
        // Allow half a second of sampling/rounding jitter. This bounded smoke
        // checks advancement across one delay, not general system-clock monotonicity.
        var lower = Math.Max(10, Math.Min(stopwatchElapsed, utcElapsed) - 5);
        var upper = Math.Max(stopwatchElapsed, utcElapsed) + 5;
        AssertTimeOfDayRoute("PUBLIC", publicBefore, publicAfter, lower, upper, stopwatchElapsed, utcElapsed);
        AssertTimeOfDayRoute("COMPILED", compiledBefore, compiledAfter, lower, upper, stopwatchElapsed, utcElapsed);
        TestContext.Out.WriteLine("TIMEOFDAY_SMOKE_COMPLETE: public and compiled UTC day-clock advancement");
    }

    private static void AssertTimeOfDayRoute(string route, (float Actual, int Lower, int Upper) before,
        (float Actual, int Lower, int Upper) after, double lower, double upper, double watchElapsed, double utcElapsed) {
        var advance = (after.Actual - before.Actual + 864000) % 864000;
        TestContext.Out.WriteLine(FormattableString.Invariant($"TIMEOFDAY_SMOKE_{route} before={before.Actual:R} beforeLower={before.Lower} beforeUpper={before.Upper} after={after.Actual:R} afterLower={after.Lower} afterUpper={after.Upper} advance={advance:R} elapsedLower={lower:R} elapsedUpper={upper:R} stopwatch={watchElapsed:R} utc={utcElapsed:R}"));
        Assert.That(float.IsFinite(before.Actual) && float.IsFinite(after.Actual) &&
            before.Actual >= 0 && before.Actual < 864000 && after.Actual >= 0 && after.Actual < 864000 &&
            before.Actual == MathF.Truncate(before.Actual) && after.Actual == MathF.Truncate(after.Actual),
            Is.True, "TIMEOFDAY_" + route + "_DAY_DECISECONDS");
        Assert.That(InDayBracket(before.Actual, before.Lower, before.Upper) &&
            InDayBracket(after.Actual, after.Lower, after.Upper), Is.True, "TIMEOFDAY_" + route + "_UTC_BRACKETS");
        Assert.That(advance >= lower && advance <= upper, Is.True, "TIMEOFDAY_" + route + "_ADVANCEMENT");
    }

    private static void AssertRealtimeSample(string route, Func<DreamValue> getter) {
        var before = DateTime.UtcNow;
        using var value = getter();
        var after = DateTime.UtcNow;
        var actual = value.MustGetValueAsFloat();
        // DreamValue(double) rounds to float. Bound the getter through the same
        // conversion, without demanding subsecond movement or strict monotonicity.
        var first = (float)((before - Epoch).TotalMilliseconds / 100);
        var last = (float)((after - Epoch).TotalMilliseconds / 100);
        var lower = Math.Min(first, last);
        var upper = Math.Max(first, last);
        Assert.That(float.IsFinite(lower) && float.IsFinite(upper) && lower > 1_000_000_000f,
            Is.True, "REALTIME_HOST_CLOCK_SUPPORTED_EPOCH");
        TestContext.Out.WriteLine("REALTIME_SAMPLE_" + route + " actual=" + actual.ToString("R", CultureInfo.InvariantCulture) +
            " lower=" + lower.ToString("R", CultureInfo.InvariantCulture) + " upper=" + upper.ToString("R", CultureInfo.InvariantCulture));
        var finite = float.IsFinite(actual);
        var largeEpoch = actual >= 1_000_000_000f;
        var inBracket = actual >= lower && actual <= upper;
        Assert.That(finite, Is.True, "REALTIME_" + route + "_FINITE");
        Assert.That(largeEpoch, Is.True, "REALTIME_" + route + "_EPOCH_MAGNITUDE");
        Assert.That(inBracket, Is.True, "REALTIME_" + route + "_UTC_BRACKET");
    }
}

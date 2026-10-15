package ai.pediamed.childgait

import ai.pediamed.childgait.data.engine.ProfileLibrary
import ai.pediamed.childgait.data.engine.SessionSynthesizer
import ai.pediamed.childgait.data.model.BodyRegion
import ai.pediamed.childgait.data.model.EvgsItem
import ai.pediamed.childgait.data.model.Limb
import ai.pediamed.childgait.data.model.SessionInput
import ai.pediamed.childgait.data.model.SessionReport
import ai.pediamed.childgait.data.model.VideoSource
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs

/**
 * The mock's whole justification is that its output is clinically coherent rather than random.
 * These tests hold it to that: a toe-walker flags the ankle and spares the pelvis, a hemiplegic
 * is asymmetric, a diplegic is bilateral, and a typically-developing child comes back clean.
 *
 * Assertions are made on **means over many sampled sessions**, not on a single report. Each
 * report is a draw from the profile's probabilities, so any individual one can be an outlier;
 * asserting per-report would give a test that fails on an unlucky seed and teaches us nothing.
 * The claim worth defending is about the profile's behaviour, and that is what is checked here.
 *
 * If someone retunes profiles.json into nonsense, this is what catches it.
 */
class ProfileCoherenceTest {

    private val library: ProfileLibrary =
        ProfileLibrary.load(File("src/main/assets/mock/profiles.json").inputStream())

    private val synthesizer = SessionSynthesizer(library)

    private fun report(index: Int): SessionReport {
        fun clip(prefix: String, bump: Long) = VideoSource(
            uri = "content://demo/$prefix/$index",
            displayName = "${prefix}_$index.mp4",
            durationMs = 4_000 + bump,
            sizeBytes = 1_500_000L + index,
        )
        return synthesizer.synthesize(
            SessionInput(
                sagittal = clip("sag", 200),
                coronal = clip("cor", 0),
            )
        )
    }

    /** Bucket many synthesized sessions by the profile that generated them. */
    private fun samplesByProfile(): Map<String, List<SessionReport>> {
        val names = library.profiles.map { it.displayName }
        val buckets = names.associateWith { mutableListOf<SessionReport>() }

        for (index in 0 until SAMPLE_COUNT) {
            val report = report(index)
            names.firstOrNull { report.patternSummary.contains(it) }
                ?.let { buckets.getValue(it) += report }
        }
        return buckets
    }

    private fun flaggedIn(report: SessionReport, region: BodyRegion): Int =
        report.aggregated.count { it.isAtypical && it.item.region == region }

    private fun flaggedOn(report: SessionReport, limb: Limb): Int =
        report.aggregated.count { it.limb == limb && it.isAtypical }

    private fun List<SessionReport>.meanOf(selector: (SessionReport) -> Int): Double =
        if (isEmpty()) 0.0 else map(selector).average()

    @Test
    fun `every profile is reachable`() {
        val samples = samplesByProfile()
        samples.forEach { (name, reports) ->
            assertTrue(
                "Profile '$name' was never drawn across $SAMPLE_COUNT sessions",
                reports.size >= MIN_SAMPLES,
            )
        }
    }

    @Test
    fun `each profile produces the deviation pattern it claims`() {
        val samples = samplesByProfile()

        samples.forEach { (name, reports) ->
            println(renderStats(name, reports))
            reports.firstOrNull()?.let { println(renderSample(it)) }
        }

        samples.getValue("typical development").let { reports ->
            val mean = reports.meanOf { it.flaggedCount }
            assertTrue("Typical development averaged $mean flagged items of 34", mean <= 6.0)
        }

        samples.getValue("idiopathic toe walking").let { reports ->
            val ankle = reports.meanOf { flaggedIn(it, BodyRegion.FOOT_ANKLE) }
            val pelvis = reports.meanOf { flaggedIn(it, BodyRegion.PELVIS) }
            assertTrue("Toe walking should load the foot/ankle, averaged $ankle", ankle >= 5.0)
            assertTrue("Toe walking should spare the pelvis, averaged $pelvis", pelvis <= 1.5)
        }

        listOf("left spastic hemiplegia", "right spastic hemiplegia").forEach { name ->
            samples.getValue(name).let { reports ->
                val asymmetry = reports.meanOf { abs(flaggedOn(it, Limb.LEFT) - flaggedOn(it, Limb.RIGHT)) }
                assertTrue("$name should be asymmetric, averaged $asymmetry", asymmetry >= 4.0)
            }
        }

        samples.getValue("spastic diplegia").let { reports ->
            val left = reports.meanOf { flaggedOn(it, Limb.LEFT) }
            val right = reports.meanOf { flaggedOn(it, Limb.RIGHT) }
            assertTrue(
                "Diplegia should be bilateral, averaged L=$left R=$right",
                left >= 6.0 && right >= 6.0,
            )
        }

        samples.getValue("in-toeing gait").let { reports ->
            val rotation = reports.meanOf { report ->
                listOf(EvgsItem.FRT, EvgsItem.KPA).sumOf { item ->
                    Limb.entries.count { report.score(item, it)?.isAtypical == true }
                }
            }
            assertTrue("In-toeing should flag rotation items, averaged $rotation", rotation >= 2.0)
        }
    }

    @Test
    fun `the demo shows meaningful variety across sessions`() {
        val flaggedCounts = (0 until SAMPLE_COUNT).map { report(it).flaggedCount }.toSet()
        assertTrue(
            "Reports should not all look alike; saw ${flaggedCounts.size} distinct flag counts",
            flaggedCounts.size >= 8,
        )
    }

    private fun renderStats(name: String, reports: List<SessionReport>): String = buildString {
        appendLine()
        appendLine("── $name ".padEnd(70, '─'))
        appendLine(
            "n=${reports.size}  " +
                "flagged=${"%.1f".format(reports.meanOf { it.flaggedCount })}/34  " +
                "L=${"%.1f".format(reports.meanOf { flaggedOn(it, Limb.LEFT) })}  " +
                "R=${"%.1f".format(reports.meanOf { flaggedOn(it, Limb.RIGHT) })}  " +
                BodyRegion.entries.joinToString("  ") { region ->
                    "${region.label.take(5)}=${"%.1f".format(reports.meanOf { flaggedIn(it, region) })}"
                }
        )
    }

    private fun renderSample(report: SessionReport): String = buildString {
        appendLine("  example: ${report.patternSummary}")
        BodyRegion.entries.forEach { region ->
            val rows = EvgsItem.entries.filter { it.region == region }.joinToString("  ") { item ->
                val left = if (report.score(item, Limb.LEFT)?.isAtypical == true) "!" else "·"
                val right = if (report.score(item, Limb.RIGHT)?.isAtypical == true) "!" else "·"
                "${item.code}:$left$right"
            }
            appendLine("    ${region.label.padEnd(12)} $rows")
        }
    }

    private companion object {
        const val SAMPLE_COUNT = 240
        const val MIN_SAMPLES = 10
    }
}

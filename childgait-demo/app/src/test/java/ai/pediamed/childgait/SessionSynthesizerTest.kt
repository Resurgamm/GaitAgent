package ai.pediamed.childgait

import ai.pediamed.childgait.data.engine.ProfileLibrary
import ai.pediamed.childgait.data.engine.SessionSynthesizer
import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.EvgsItem
import ai.pediamed.childgait.data.model.GaitView
import ai.pediamed.childgait.data.model.Limb
import ai.pediamed.childgait.data.model.SessionInput
import ai.pediamed.childgait.data.model.VideoSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class SessionSynthesizerTest {

    private val library: ProfileLibrary =
        ProfileLibrary.load(File("src/main/assets/mock/profiles.json").inputStream())

    private fun synthesizer() = SessionSynthesizer(library)

    private fun clip(name: String, durationMs: Long = 4_200, sizeBytes: Long = 1_800_000) =
        VideoSource(
            uri = "content://media/external/video/media/$name",
            displayName = name,
            durationMs = durationMs,
            sizeBytes = sizeBytes,
        )

    private fun input(
        sag: String = "sag.mp4",
        cor: String = "cor_001.mp4",
    ) = SessionInput(
        sagittal = clip(sag),
        coronal = clip(cor, durationMs = 3_800, sizeBytes = 1_600_000),
    )

    @Test
    fun `same clips yield an identical report every time`() {
        val session = input()
        val first = synthesizer().synthesize(session)
        val second = synthesizer().synthesize(session)

        assertEquals(first.patternSummary, second.patternSummary)
        assertEquals(first.aggregated, second.aggregated)
        assertEquals(first.clipQuality, second.clipQuality)
    }

    @Test
    fun `different clips yield different reports`() {
        val a = synthesizer().synthesize(input("a_sag.mp4", "a_c.mp4"))
        val b = synthesizer().synthesize(input("b_sag.mp4", "b_c.mp4"))

        val differs = a.patternSummary != b.patternSummary ||
            a.aggregated.map { it.label } != b.aggregated.map { it.label }
        assertTrue("Distinct clip pairs should not produce identical reports", differs)
    }

    @Test
    fun `sagittal limb scores are mirrored`() {
        val report = synthesizer().synthesize(input())
        EvgsItem.forView(GaitView.SAGITTAL).forEach { item ->
            val left = report.score(item, Limb.LEFT)!!
            val right = report.score(item, Limb.RIGHT)!!
            assertEquals(left.label, right.label)
            assertEquals(left.confidence, right.confidence, 1e-6f)
        }
    }

    @Test
    fun `every item is scored for both limbs`() {
        val report = synthesizer().synthesize(input())

        assertEquals(34, report.aggregated.size)
        EvgsItem.entries.forEach { item ->
            Limb.entries.forEach { limb ->
                assertTrue(
                    "Missing score for ${limb.code}-${item.code}",
                    report.aggregated.any { it.item == item && it.limb == limb },
                )
            }
        }
    }

    @Test
    fun `the two planes partition the items with no overlap and no gap`() {
        val sagittal = EvgsItem.forView(GaitView.SAGITTAL).toSet()
        val coronal = EvgsItem.forView(GaitView.CORONAL).toSet()

        assertEquals(emptySet<EvgsItem>(), sagittal intersect coronal)
        assertEquals(EvgsItem.entries.toSet(), sagittal union coronal)
        assertEquals(11, sagittal.size)
        assertEquals(6, coronal.size)
    }

    @Test
    fun `each score is attributed to the matching camera slot`() {
        val report = synthesizer().synthesize(input())

        report.aggregated.forEach { score ->
            val clip = report.clipFor(score.item, score.limb)
            assertEquals(score.item.view, clip.view)
            when (score.item.view) {
                GaitView.SAGITTAL -> assertEquals(CameraSlot.SAGITTAL, clip.slot)
                GaitView.CORONAL -> assertEquals(CameraSlot.CORONAL, clip.slot)
            }
        }
    }

    @Test
    fun `per-clip score counts match the slot split`() {
        val report = synthesizer().synthesize(input())

        assertEquals(22, report.scoresFrom(CameraSlot.SAGITTAL).size)
        assertEquals(12, report.scoresFrom(CameraSlot.CORONAL).size)
        assertEquals(22, report.scoresFrom(GaitView.SAGITTAL).size)
        assertEquals(12, report.scoresFrom(GaitView.CORONAL).size)
    }

    @Test
    fun `confidences stay in a plausible range`() {
        val report = synthesizer().synthesize(input())
        report.aggregated.forEach { score ->
            assertTrue(
                "Confidence out of range for ${score.key}: ${score.confidence}",
                score.confidence in 0.50f..0.99f,
            )
        }
    }

    @Test
    fun `each clip gets its own quality score`() {
        val report = synthesizer().synthesize(input())
        CameraSlot.entries.forEach { slot ->
            assertTrue(
                "Missing or implausible quality for $slot",
                report.qualityOf(slot) in 0.60f..1.0f,
            )
        }
    }

    @Test
    fun `profiles library is well formed`() {
        assertNotEquals(0, library.profiles.size)
        library.profiles.forEach { profile ->
            assertTrue("${profile.id} has no weight", profile.weight > 0f)
            EvgsItem.entries.forEach { item ->
                Limb.entries.forEach { limb ->
                    val probability = profile.probabilityOf(item, limb)
                    assertTrue(
                        "${profile.id}/${item.code}/${limb.code} out of range: $probability",
                        probability in 0f..1f,
                    )
                }
            }
        }
    }
}

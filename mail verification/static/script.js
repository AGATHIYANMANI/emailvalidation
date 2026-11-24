
const textTab = document.getElementById("textTab");
const fileTab = document.getElementById("fileTab");

const textSection = document.getElementById("textSection");
const fileSection = document.getElementById("fileSection");

const emailText = document.getElementById("emailText");
const emailFile = document.getElementById("emailFile");

let selectedMode = "text";

// Switch to text input
textTab.addEventListener("click", () => {

    selectedMode = "text";

    textSection.classList.remove("hidden");
    fileSection.classList.add("hidden");

    textTab.classList.add("active");
    fileTab.classList.remove("active");

});

// Switch to file upload
fileTab.addEventListener("click", () => {

    selectedMode = "file";

    fileSection.classList.remove("hidden");
    textSection.classList.add("hidden");

    fileTab.classList.add("active");
    textTab.classList.remove("active");

});

// Analyze email
document.getElementById("emailForm")
.addEventListener("submit", async function(event) {

    event.preventDefault();

    const form = document.getElementById("emailForm");
    const formData = new FormData(form);

    const result = document.getElementById("result");
    const prediction = document.getElementById("prediction");
    const words = document.getElementById("words");

    const downloadBtn = document.getElementById("downloadBtn");
    const submitBtn = document.getElementById("submitBtn");

    if (selectedMode === "text") {

        if (!emailText.value.trim()) {
            alert("Please enter email content.");
            return;
        }

        formData.delete("email_file");

    } else {

        if (!emailFile.files.length) {
            alert("Please upload an email file.");
            return;
        }

        formData.delete("email_text");
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Analyzing...";

    result.classList.add("hidden");
    downloadBtn.classList.add("hidden");

    try {

        const response = await fetch("/predict", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Prediction failed.");
        }

        result.classList.remove("hidden");

        prediction.textContent =
            "Result: " + data.prediction;

        prediction.style.color =
            data.prediction === "Spam" ? "red" : "green";

        document.getElementById("accuracy").textContent =
            data.accuracy + "%";

        words.innerHTML = "";

        if (data.suspicious_words.length > 0) {

            data.suspicious_words.forEach(word => {

                const span = document.createElement("span");

                span.className = "word";
                span.textContent = word;

                words.appendChild(span);

            });

        } else {

            words.textContent =
                "No spam-associated words found.";

        }

        // Show PDF download
        downloadBtn.href = "/download/" + data.id;
        downloadBtn.classList.remove("hidden");

        result.scrollIntoView({ behavior: "smooth" });

    } catch (error) {

        alert(error.message);

    } finally {

        submitBtn.disabled = false;
        submitBtn.textContent = "Analyze Email";

    }

});
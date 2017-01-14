

function parsesize (size) {
	if (size == "T") size = "Tiny";
	if (size == "S") size = "Small";
	if (size == "M") size = "Medium";
	if (size == "L") size = "Large";
	if (size == "H") size = "Huge";
	if (size == "G") size = "Gargantuan";
	return size;
}

function parseschool (school) {
	if (school == "A") return "abjuration";
	if (school == "EV") return "evocation";
	if (school == "EN") return "enchantment";
	if (school == "I") return "illusion";
	if (school == "D") return "divination";
	if (school == "N") return "necromancy";
	if (school == "T") return "transmutation";
	if (school == "C") return "conjuration";
	return false;
}

function parsespelllevel (level) {
	if (isNaN (level)) return false;
	if (level === "0") return "cantrip"
	if (level === "2") return level+"nd";
	if (level === "3") return level+"rd";
	if (level === "1") return level+"st";
	return level+"th";
}

function asc_sort(a, b){
    return ($(b).text()) < ($(a).text()) ? 1 : -1;
}

function dec_sort(a, b){
    return ($(b).text()) > ($(a).text()) ? 1 : -1;
}

window.onload = loadspells;

function loadspells() {
	tabledefault = $("#stats").html();

	var spelllist = spelldata.compendium.spell;

		for (var i = 0; i < spelllist.length; i++) {
			var curspell = spelllist[i];
			var name = curspell.name;
			var leveltext = "";
			if (curspell.level !== "0") leveltext = "level"
			var isritual="";
			if (curspell.ritual === "YES") isritual = " (ritual)";

			$("ul.spells").append("<li id='"+i+"' data-link='"+encodeURIComponent(name).toLowerCase().replace("'","%27")+"' data-name='"+encodeURIComponent(name).replace("'","%27")+"'><span class='name'>"+curspell.name+"</span> <span class='level'>"+parsespelllevel(curspell.level)+" "+leveltext+isritual+"</span> <span class='school'>"+parseschool (curspell.school)+"</span> <span class='classes'>"+curspell.classes+"</span> </li>");

			if (!$("select.levelfilter:contains('"+parsespelllevel(curspell.level)+"')").length) {
				$("select.levelfilter").append("<option value='"+curspell.level+"'>"+parsespelllevel(curspell.level)+"</option>");
			}

			if (!$("select.schoolfilter:contains('"+parseschool (curspell.school)+"')").length) {
				$("select.schoolfilter").append("<option value='"+parseschool (curspell.school)+"'>"+parseschool (curspell.school)+"</option>");
			}

			var classlist = curspell.classes.split(",");
			for (var a = 0; a < classlist.length; a++) {
				if (classlist[a][0] === " ") classlist[a] = classlist[a].replace(/^\s+|\s+$/g, "")
				if (!$("select.classfilter option[value='"+classlist[a]+"']").length) {
					$("select.classfilter").append("<option title=\""+classlist[a]+"\" value='"+classlist[a]+"'>"+classlist[a]+"</option>")
				}
			}

		}

		$("select.levelfilter option").sort(asc_sort).appendTo('select.levelfilter');
		$("select.levelfilter option[value=1]").before($("select.levelfilter option[value=All]"));
		$("select.levelfilter option[value=1]").before($("select.levelfilter option[value=0]"));
		$("select.levelfilter").val("All");

		$("select.schoolfilter option").sort(asc_sort).appendTo('select.schoolfilter');
		$("select.schoolfilter").val("All");

		$("select.classfilter option").sort(asc_sort).appendTo('select.classfilter');
		$("select.classfilter").val("All");

		var options = {
			valueNames: ['name', 'level', 'school', 'classes'],
			listClass: "spells"
		}

		var spellslist = new List("listcontainer", options);
		spellslist.sort ("name")

		$("ul.list li").mousedown(function(e) {
			if (e.which === 2) {
				console.log("#"+$(this).attr("data-link").toLowerCase())
				window.open("#"+$(this).attr("data-link").toLowerCase(), "_blank").focus();
				e.preventDefault();
				e.stopPropagation();
				return;
			}
		});

		$("ul.list li").click(function(e) {
			usespell($(this).attr("id"));
			document.title = decodeURIComponent($(this).attr("data-name")).replace("%27","'") + " - 5etools Spells";
			window.location = "#"+$(this).attr("data-link").toLowerCase();
		});

		if (window.location.hash.length) {
			$("ul.list li[data-link='"+window.location.hash.split("#")[1].toLowerCase()+"']:eq(0)").click();
		} else $("ul.list li:eq(0)").click();

		$("form#filtertools select").change(function(){
			var levelfilter = $("select.levelfilter").val();
			if (levelfilter !== "All") {
				levelfilter = parsespelllevel (levelfilter);
				if (levelfilter !== "cantrip") {
					levelfilter = levelfilter + " level"
				} else levelfilter = "cantrip ";
				if ($(".ritualfilter").val() === "Rituals") levelfilter = levelfilter + " (ritual)"
			} else if ($(".ritualfilter").val() === "Rituals") levelfilter = "(ritual)"

			var schoolfilter = $("select.schoolfilter").val();
			var classfilter = $("select.classfilter").val();

			spellslist.filter(function(item) {
				var rightlevel = false;
				var rightschool = false;
				var rightclass = false;
				if (levelfilter === "All" || item.values().level.indexOf(levelfilter) !== -1) rightlevel = true;
				if (schoolfilter === "All" || item.values().school === schoolfilter) rightschool = true;
				var classes = item.values().classes.split(", ");
				for (var c = 0; c < classes.length; c++) {
					if (classes[c] === classfilter) rightclass = true;
				}
				if (classfilter === "All") rightclass = true;
				if (rightlevel && rightschool && rightclass) return true;
				return false;
			});
		});
}

function usespell (id) {
			$("#stats").html(tabledefault);
			var spelllist = spelldata.compendium.spell;
			var curspell = spelllist[id];

			$("th#name").html(curspell.name);

			$("td span#school").html(parseschool(curspell.school));
			if (curspell.level === "0") {
				$("td span#school").css('textTransform', 'capitalize');
				$("td span#level").css('textTransform', 'lowercase!important');
				$("td span#level").html(" cantrip").detach().appendTo("td span#school");
			} else {
				$("td span#school").css('textTransform', 'lowercase');
				$("td span#level").html(parsespelllevel (curspell.level)+"-level");
			}

			if (curspell.ritual === "YES") {
				$("td span#ritual").show();
			} else $("td span#ritual").hide();

			$("td#components span").html(curspell.components)
			$("td#range span").html(curspell.range)
			$("td#castingtime span").html(curspell.time)
			$("td#duration span").html(curspell.duration)

			$("tr.text").remove();
			var textlist = curspell.text;
			var texthtml = "";

			if (textlist[0].length === 1) {
				texthtml = "<p>"+textlist+"</p>";
			} else for (var i = 0; i < textlist.length; i++) {
				if (!textlist[i]) continue;
				texthtml = texthtml + "<p>"+textlist[i].replace("At Higher Levels: ", "<strong>At Higher Levels:</strong> ").replace("This spell can be found in the Elemental Evil Player's Companion","")+"</p>";
			}
			$("tr#text").after("<tr class='text'><td colspan='6' class='text"+i+"'>"+texthtml+"</td></tr>");

			$("td#classes span").html(curspell.classes);

			return;
		};

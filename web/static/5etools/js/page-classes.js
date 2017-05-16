

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
function tagcontent (curitem, tag, multi=false) {
	if (!curitem.getElementsByTagName(tag).length) return false;
	return curitem.getElementsByTagName(tag)[0].childNodes[0].nodeValue;
}

function asc_sort(a, b){
	return ($(b).text()) < ($(a).text()) ? 1 : -1;
}

function dec_sort(a, b){
	return ($(b).text()) > ($(a).text()) ? 1 : -1;
}

window.onload = loadspells;
var tabledefault="";
var classtabledefault ="";

function loadspells() {
	tabledefault = $("#stats").html();
	statsprofdefault = $("#statsprof").html();
	classtabledefault = $("#classtable").html();

	var classlist = classdata.compendium.class;

	for (var i = 0; i < classlist.length; i++) {
		var curclass = classlist[i];

		$("ul.classes").append("<li id='"+i+"' data-link='"+encodeURI(curclass.name)+"'><span class='name'>"+curclass.name+"</span></li>");

	}

	var options = {
		valueNames: ['name'],
		listClass: "classes"
	}

	var classlist = new List("listcontainer", options);
	classlist.sort ("name");

	$("ul.list li").mousedown(function(e) {
		if (e.which === 2) {
			window.open("#"+$(this).attr("data-link"), "_blank").focus();
			e.preventDefault();
			e.stopPropagation();
			return;
		}
	});

	$("ul.list li").click(function(e) {
		var subclass = window.location.hash.split(/\,/)[1];
		window.location.hash = "#"+$(this).attr("data-link")+",";
		if (subclass !== "undefined") {
			window.location.hash += subclass;
		}
		useclass($(this).attr("id"));
		if (!$("div#subclasses > span:contains("+(decodeURIComponent(window.location.hash).split(/\,/)[1])+")").length) {
			window.location.hash = window.location.hash.replace(/\,.*/g,",");
		}

		document.title = decodeURI($(this).attr("data-link")) + " - 5etools Classes";
	});

	if (window.location.hash.length) {
		$("ul.list li[data-link='"+window.location.hash.split(/\#|\,/)[1]+"']:eq(0)").click();
		if (window.location.hash.split(/\,/)[1].length) {
			$("div#subclasses > span:contains("+(decodeURIComponent(window.location.hash).split(/\,/)[1])+")").click()
			if (!$("div#subclasses > span:contains("+(decodeURIComponent(window.location.hash).split(/\,/)[1])+")").length) {
				window.location.hash = window.location.hash.replace(/\,.*/g,",");
			}
		}
	} else $("ul.list li:eq(0)").click();

}

function useclass (id) {
	$("#stats").html(tabledefault);
	$("#statsprof").html(statsprofdefault);
	$("#classtable").html(classtabledefault);
	var classlist = classdata.compendium.class;
	var curclass = classlist[id];

	$("th#name").html(curclass.name);

	$("td#hp div#hitdice span").html("1d"+curclass.hd);
	$("td#hp div#hp1stlevel span").html(curclass.hd+" + your Constitution modifier");
	$("td#hp div#hphigherlevels span").html("1d"+curclass.hd+" (or "+(curclass.hd/2+1)+") + your Constitution modifier per "+curclass.name+" level after 1st");

	$("td#prof div#saves span").html(curclass.proficiency);

	$("tr:has(.slotlabel)").hide();
	$("#classtable tr").not(":has(th)").append("<td class='featurebuffer'></td>");

	var subclasses = [];
	for (var i = curclass.autolevel.length-1; i >= 0; i--) {
		var curlevel = curclass.autolevel[i];

// spell slots and table data
		if (!curlevel.feature) {
			if (curlevel.slots) {
				$("tr:has(.slotlabel)").show();
				if (curlevel.slots.__text) curlevel.slots = curlevel.slots.__text;
				var curslots = curlevel.slots.split(",");
				if (curslots[0] !== "0" && $("th.slotbuffer").attr("colspan") < 4) {
					$("#classtable td.border").attr("colspan", parseInt($("#classtable td.border").attr("colspan"))+1);
					$("th.slotbuffer").attr("colspan", parseInt($("th.slotbuffer").attr("colspan"))+1);
				}
				$("th.slotlabel").attr("colspan", curslots.length-1);
				if (curslots.length > 1) $(".featurebuffer").hide();

				for (var a = 0; a < curslots.length; a++) {
					if (curslots[a] === "0") continue;
					$(".spellslots"+a).show();
					$("tr#level"+curlevel._level+" td.spellslots"+a).html(curslots[a]);
				}
			}

			if (curlevel.spellsknown) {
				if (!$(".spellsknown").length) {
					$("th.spellslots0").after("<th class='spellsknown newfeature'>Spells Known</th>");
					$("td.spellslots0").after("<td class='spellsknown newfeature'></td>");
					$("#classtable th.border").attr("colspan", parseInt($("#classtable th.border").attr("colspan"))+1);
					$("th.slotbuffer").attr("colspan", parseInt($("th.slotbuffer").attr("colspan"))+1);
				}
				$("tr#level"+curlevel._level+" td.spellsknown").html(curlevel.spellsknown);
			}

			if (curlevel.invocationsknown) {
				if (!$(".invocationsknown").length) {
					$("th.spellslots5").after("<th class='spellslots newfeature'>Spell Slots</th> <th class='slotlevel newfeature'>Slot Level</th> <th class='invocationsknown newfeature'>Invocations Known</th>");
					$("td.spellslots5").after("<td class='spellslots newfeature'></td> <td class='slotlevel newfeature'></td> <td class='invocationsknown newfeature'>Invocations Known</td>");
					$("#classtable th.border").attr("colspan", parseInt($("#classtable th.border").attr("colspan"))+3);
				}
				$(".spellslots5").hide();
				$("tr#level"+curlevel._level+" td.spellslots").html(curlevel.spellslots);
				$("tr#level"+curlevel._level+" td.slotlevel").html(curlevel.slotlevel);
				$("tr#level"+curlevel._level+" td.invocationsknown").html(curlevel.invocationsknown);
				$("tr:has(.slotlabel)").hide();
			}

			if (curlevel.rages) {
				if (!$(".rages").length) {
					$("th.spellslots0").before("<th class='rages newfeature'>Rages</th> <th class='ragedamage newfeature'>Rage Damage</th>");
					$("td.spellslots0").before("<td class='rages newfeature'></td> <td class='ragedamage newfeature'></td>");
					$("#classtable th.border").attr("colspan", parseInt($("#classtable th.border").attr("colspan"))+2);
				}
				$("tr#level"+curlevel._level+" td.rages").html(curlevel.rages);
				$("tr#level"+curlevel._level+" td.ragedamage").html(curlevel.ragedamage);
			}

			if (curlevel.martialarts) {
				if (!$(".kipoints").length) {
					$("th.pb").after("<th class='martialarts newfeature'>Martial Arts</th> <th class='kipoints newfeature'>Ki Points</th> <th class='unarmoredmovement newfeature'>Unarmored Movement</th>");
					$("td.pb").after("<td class='martialarts newfeature'></td> <td class='kipoints newfeature'></td> <td class='unarmoredmovement newfeature'></td>");
					$("#classtable td.border").attr("colspan", parseInt($("#classtable td.border").attr("colspan"))+3);
					$("th.slotbuffer").attr("colspan", $("th.slotbuffer").attr("colspan")+3);
				}
				$("tr#level"+curlevel._level+" td.martialarts").html(curlevel.martialarts);
				$("tr#level"+curlevel._level+" td.kipoints").html(curlevel.kipoints);
				$("tr#level"+curlevel._level+" td.unarmoredmovement").html(curlevel.unarmoredmovement);
			}

			if (curlevel.sneakattack) {
				if (!$(".sneakattack").length) {
					$("th.pb").after("<th class='sneakattack newfeature'>Sneak Attack</th>");
					$("td.pb").after("<td class='sneakattack newfeature'></td>");
					$("#classtable td.border").attr("colspan", parseInt($("#classtable td.border").attr("colspan"))+1);
					$("th.slotbuffer").attr("colspan", parseInt($("th.slotbuffer").attr("colspan"))+1);
				}
				$("tr#level"+curlevel._level+" td.sneakattack").html(curlevel.sneakattack);
			}

			if (curlevel.sorcerypoints) {
				if (!$(".sorcerypoints").length) {
					$("th.pb").after("<th class='sorcerypoints newfeature'>Sorcery Points</th>");
					$("td.pb").after("<td class='sorcerypoints newfeature'></td>");
					$("#classtable td.border").attr("colspan", parseInt($("#classtable td.border").attr("colspan"))+1);
					console.log($("#classtable td.border").attr("colspan"))
					$("th.slotbuffer").attr("colspan", parseInt($("th.slotbuffer").attr("colspan"))+1);
				}
				$("tr#level"+curlevel._level+" td.sorcerypoints").html(curlevel.sorcerypoints);
			}

// other features
		} else for (var a = curlevel.feature.length-1; a >= 0; a--) {
			var curfeature = curlevel.feature[a];


			if (curfeature._optional === "YES") {
				subclasses.push(curfeature);
			}

			var subfeature = (curfeature.suboption === "YES") ? " subfeature" : "";
			var issubclass = (curfeature.subclass !== "undefined" && curfeature.parent === curfeature.subclass)  ? "" : " subclass";

			if (curfeature.name === "Starting Proficiencies") {
				$("td#prof div#armor span").html(curfeature.text[1].split(":")[1]);
				$("td#prof div#weapons span").html(curfeature.text[2].split(":")[1]);
				$("td#prof div#tools span").html(curfeature.text[3].split(":")[1]);
				$("td#prof div#skills span").html(curfeature.text[4].split(":")[1]);
				continue;
			}

			if (curfeature.name === "Starting Equipment") {
				$("#equipment div").html("<p>"+curfeature.text.join("</p><p>"));
				continue;
			}

			// write out list to class table
			var multifeature = "";
			if (curlevel.feature.length !== 1 && a !== 0) multifeature = ", ";
			if (curfeature._optional !== "YES") $("tr#level"+curlevel._level+" td.features").prepend(multifeature+"<a href='"+window.location.hash+"' data-link='"+encodeURIComponent(curfeature.name).replace("'","%27")+"'>"+curfeature.name+"</a>")

			// display features in bottom section
			$("#features").after("<tr><td colspan='6' class='feature"+subfeature+issubclass+"' data-subclass='"+curfeature.subclass+"'><strong id='feature"+encodeURI (curfeature.name)+"'>"+curfeature.name+"</strong> <p>"+curfeature.text.join("</p><p>")+"</td></tr>");
		}

	}

	$("td.features, td.slots, td.newfeature").each(function() {
		if ($(this).html() === "") $(this).html("—")
	});

	$(".feature:contains('Maneuver: ')").css("font-size","0.8em");

	$("div#subclasses span").remove();
	var prevsubclass = 0;
	for (var i = 0; i < subclasses.length; i++) {

		if (typeof subclasses[i].issubclass !== "undefined" && subclasses[i].issubclass !== "YES") {
			$(".feature[data-subclass='"+subclasses[i].subclass+"']").hide();
			continue;
		}

		if (!prevsubclass) prevsubclass = subclasses[i].subclass;

		if (subclasses[i].issubclass === "YES") $("div#subclasses").prepend("<span data-subclass='"+subclasses[i].name+"'><em style='display: none;'>"+subclasses[i].name.split(": ")[0]+": </em><span>"+subclasses[i].name.split(": ")[1]+"</span></span>")

	}

	$("div#subclasses > span").sort(asc_sort).appendTo("div#subclasses");

	$("div#subclasses > span").click(function() {
		var name = $(this).children("span").text();
		if ($(this).hasClass("active")) {
			$(".feature").show();
			$(this).removeClass("active");
			window.location.hash = window.location.hash.replace(/\,.*/g,",");
			return;
		}

		$("div#subclasses span.active").removeClass("active");
		$(this).addClass("active");

		window.location.hash = window.location.hash.replace(/\,\S*/g, ","+encodeURIComponent(name).replace("'","%27"))

		$(".feature[data-subclass!='"+$(this).text()+"'][data-subclass!='undefined']").hide();
		$(".feature[data-subclass='"+$(this).text()+"']").show();
	})

	//	$("div#subclasses > span").first().click();

		$(".features a").click(function() {
			$("#stats").parent().scrollTop(0)
			$("#stats").parent().scrollTop($("#stats").parent().scrollTop() + $("td.feature strong[id='feature"+$(this).attr("data-link")+"']").position().top)
			$("html, body").scrollTop($("td.feature strong[id='feature"+$(this).attr("data-link")+"']").position().top);
		})

	return;
};

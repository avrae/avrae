

function parsesource (src) {
	source = src;
	if (source == " monster manual") source = "MM";
	if (source == " Volo's Guide") source = "VGM";
	if (source == " elemental evil") source = "PotA";
	if (source == " storm kings thunder") source = "SKT";
	if (source == " tyranny of dragons") source = "ToD";
	if (source == " out of the abyss") source = "OotA";
	if (source == " curse of strahd") source = "CoS";
	if (source == " lost mine of phandelver") source = "LMoP";
	if (source == " tome of beasts") source = "ToB 3pp";
	return source;
}

function parsesourcename (src) {
	source = src;
	if (source == " monster manual") source = "Monster Manual";
	if (source == " Volo's Guide") source = "Volo's Guide to Monsters";
	if (source == " elemental evil") source = "Princes of the Apocalypse";
	if (source == " storm kings thunder") source = "Storm King's Thunder";
	if (source == " tyranny of dragons") source = "Tyranny of Dragons";
	if (source == " out of the abyss") source = "Out of the Abyss";
	if (source == " curse of strahd") source = "Curse of Strahd";
	if (source == " lost mine of phandelver") source = "Lost Mine of Phandelver";
	if (source == " tome of beasts") source = "Tome of Beasts (3pp)";
	return source;
}

function parsesize (size) {
	if (size == "T") size = "Tiny";
	if (size == "S") size = "Small";
	if (size == "M") size = "Medium";
	if (size == "L") size = "Large";
	if (size == "H") size = "Huge";
	if (size == "G") size = "Gargantuan";
	return size;
}

var xpchart = [200, 450, 700, 1100, 1800, 2300, 2900, 3900, 5000, 5900, 7200, 8400, 10000, 11500, 13000, 15000, 18000, 20000, 22000, 25000, 30000, 41000, 50000, 62000, 75000, 90000, 105000, 102000, 135000, 155000]

function addCommas(intNum) {
	return (intNum + '').replace(/(\d)(?=(\d{3})+$)/g, '$1,');
}

function parsecr (cr) {
	if (cr === "0") return "0 or 10"
	if (cr === "1/8") return "25"
	if (cr === "1/4") return "50"
	if (cr === "1/2") return "100"
	return addCommas (xpchart[parseInt(cr)-1]);
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

window.onload = loadmonsters;

function loadmonsters() {
	tabledefault = $("#stats").html();

	monsters = monsterdata.compendium.monster;

	// parse all the monster data
	for (var i = 0; i < monsters.length; i++) {
		var name = monsters[i].name;
		var source = monsters[i].type.split(",");
		var type = source.slice(0, source.length-1).join(",")
		type = type.split(", Volo's Guide")[0];
		source = source[source.length - 1]
		origsource = parsesourcename(source);
		source = parsesource(source);

		var cr = monsters[i].cr;


		$("ul#monsters").append("<li id="+i+" data-link='"+encodeURIComponent(name).replace("'","%27")+"'><span class='name'>"+name+"</span> <span title=\""+origsource+"\" class='source source"+source+"'>("+source+")</span> <span class='type'>Type: "+type+"</span> <span class='cr'>CR "+cr+" </span></li>");

		if (!$("select.typefilter:contains('"+type+"')").length) {
			$("select.typefilter").append("<option value='"+type+"'>"+type+"</option>")
		}
		if (!$("select.sourcefilter option[value='"+parsesource(source)+"']").length) {
			$("select.sourcefilter").append("<option title=\""+source+"\" value='"+parsesource(source)+"'>"+parsesource(source)+"</option>")
		}
		if (!$("select.crfilter option[value='"+cr+"']").length) {
			$("select.crfilter").append("<option title=\""+cr+"\" value='"+cr+"'>"+cr+"</option>")
		}
	}

	$("select.typefilter option").sort(asc_sort).appendTo('select.typefilter');
	$("select.typefilter").val("All");

	$("select.crfilter option").sort(asc_sort).appendTo('select.crfilter');
	for (var b = 9; b > 1; b--) {
		$("select.crfilter option[value=1]").after($("select.crfilter option[value="+b+"]"))
	}
	$("select.crfilter option[value=1]").before($("select.crfilter option[value='1/8']"))
	$("select.crfilter option[value=1]").before($("select.crfilter option[value='1/4']"))
	$("select.crfilter option[value=1]").before($("select.crfilter option[value='1/2']"))
	$("select.crfilter option[value=0]").before($("select.crfilter option[value=All]"))

	var options = {
		valueNames: ['name', 'source', 'type', 'cr']
	}

	var monlist = new List("monstercontainer", options)
	monlist.sort("name");

	$("ul.list li").mousedown(function(e) {
		if (e.which === 2) {
			window.open("#"+$(this).attr("data-link"), "_blank").focus();
			e.preventDefault();
			e.stopPropagation();
			return;
		}
	});

	$("ul.list li").click(function(e) {
		usemonster($(this).attr("id"));
		document.title = decodeURIComponent($(this).attr("data-link")).replace("%27","'") + " - 5etools Bestiary";
		window.location = "#"+$(this).attr("data-link");
	});

	if (window.location.hash.length) {
		$("ul.list li[data-link='"+window.location.hash.split("#")[1]+"']:eq(0)").click();
	} else $("ul.list li:eq(0)").click();

	$("form#filtertools select").change(function(){
		var typefilter = "Type: "+$("select.typefilter").val();
		var sourcefilter = $("select.sourcefilter").val();
		var crfilter = "CR "+$("select.crfilter").val()+" ";
		var thirdpartyfilter = $("select.3ppfilter").val()+" ";

		monlist.filter(function(item) {
			var righttype = false;
			var rightsource = false;
			var rightcr = false;
			var rightparty = false;

			if (typefilter === "Type: All" || item.values().type === typefilter) righttype = true;
			if (sourcefilter === "All" || item.values().source === "("+sourcefilter+")") rightsource = true;
			if (crfilter === "CR All " || item.values().cr === crfilter) rightcr = true;
			if (thirdpartyfilter === "All " || item.values().source.indexOf("3pp") === -1) rightparty = true;
			if (righttype && rightsource && rightcr && rightparty) return true;
			return false;
		});
	});

	$("#filtertools span.sort").on("click", function() {
		if ($(this).attr("sortby") === "asc") {
			$(this).attr("sortby", "desc");
		} else $(this).attr("sortby", "asc");
		monlist.sort($(this).attr("sort"), { order: $(this).attr("sortby"), sortFunction: sortmonsters });
	});

}

function asc_sort(a, b){
	return ($(b).text()) < ($(a).text()) ? 1 : -1;
}

function desc_sort(a, b){
	return ($(b).text()) > ($(a).text()) ? 1 : -1;
}

function sortmonsters(a, b, o) {
	if (o.valueName === "name") {
		return ((b._values.name.toLowerCase()) > (a._values.name.toLowerCase())) ? 1 : -1;
	}

	if (o.valueName === "type") {
		return ((b._values.type.toLowerCase()) > (a._values.type.toLowerCase())) ? 1 : -1;
	}

	if (o.valueName === "source") {
		return ((b._values.source.toLowerCase()) > (a._values.source.toLowerCase())) ? 1 : -1;
	}

	if (o.valueName === "cr") {
		acr = a._values.cr.replace("CR ", "").replace(" ", "")
		bcr = b._values.cr.replace("CR ", "").replace(" ", "")
		if (acr === "1/2") acr = "-1";
		if (bcr === "1/2") bcr = "-1";
		if (acr === "1/4") acr = "-2";
		if (bcr === "1/4") bcr = "-2";
		if (acr === "1/8") acr = "-3";
		if (bcr === "1/8") bcr = "-3";
		if (acr === "0") acr = "-4";
		if (bcr === "0") bcr = "-4";
		return (parseInt(bcr) > parseInt(acr)) ? 1 : -1;
	}

	return 1;

}

function usemonster (id) {
	$("#stats").html(tabledefault);
	monsters = monsterdata.compendium.monster;
	var mon = monsters[id];
	var name = mon.name;
	var source = mon.type.split(",");
	source = source[source.length - 1]
	origsource = parsesourcename(source);
	source = parsesource(source);
	$("th#name").html("<span title=\""+origsource+"\" class='source source"+source+"'>"+source+"</span> "+name);

	var size = parsesize (mon.size);
	$("td span#size").html(size);

	var type = mon.type.split(",");
	type = type.slice(0, type.length-1).join(",");
	$("td span#type").html(type);

	var alignment = mon.alignment;
	$("td span#alignment").html(alignment);

	var ac = mon.ac;
	$("td span#ac").html(ac);

	var hp = mon.hp;
	$("td span#hp").html(hp);

	var speed = mon.speed;
	$("td span#speed").html(speed);

	var str = mon.str;
	var strmod = Math.floor((str - 10) / 2);
	if (strmod >= 0) strmod = "+"+strmod;
	$("td#str span.score").html(str);
	$("td#str span.mod").html(strmod);

	var dex = mon.dex;
	var dexmod = Math.floor((dex - 10) / 2);
	if (dexmod >= 0) dexmod = "+"+dexmod;
	$("td#dex span.score").html(dex);
	$("td#dex span.mod").html(dexmod);

	var con = mon.con;
	var conmod = Math.floor((con - 10) / 2);
	if (conmod >= 0) conmod = "+"+conmod;
	$("td#con span.score").html(con);
	$("td#con span.mod").html(conmod);

	var ints = mon.int;
	var intmod = Math.floor((ints - 10) / 2);
	if (intmod >= 0) intmod = "+"+intmod;
	$("td#int span.score").html(ints);
	$("td#int span.mod").html(intmod);

	var wis = mon.wis;
	var wismod = Math.floor((wis - 10) / 2);
	if (wismod >= 0) wismod = "+"+wismod;
	$("td#wis span.score").html(wis);
	$("td#wis span.mod").html(wismod);

	var cha = mon.cha;
	var chamod = Math.floor((cha - 10) / 2);
	if (chamod >= 0) chamod = "+"+chamod;
	$("td#cha span.score").html(cha);
	$("td#cha span.mod").html(chamod);

	var saves = mon.save;
	if (saves && saves.length > 0) {
		$("td span#saves").parent().show();
		$("td span#saves").html(saves);
	} else {
		$("td span#saves").parent().hide();
	}

	var skills = mon.skill;
	if (skills && skills.length > 0 && skills[0]) {
		$("td span#skills").parent().show();
		$("td span#skills").html(skills);
	} else {
		$("td span#skills").parent().hide();
	}

	var dmgvuln = mon.vulnerable;
	if (dmgvuln && dmgvuln.length > 0) {
		$("td span#dmgvuln").parent().show();
		$("td span#dmgvuln").html(dmgvuln);
	} else {
		$("td span#dmgvuln").parent().hide();
	}

	var dmgres = mon.resist;
	if (dmgres && dmgres.length > 0) {
		$("td span#dmgres").parent().show();
		$("td span#dmgres").html(dmgres);
	} else {
		$("td span#dmgres").parent().hide();
	}

	var dmgimm = mon.immune;
	if (dmgimm && dmgimm.length > 0) {
		$("td span#dmgimm").parent().show();
		$("td span#dmgimm").html(dmgimm);
	} else {
		$("td span#dmgimm").parent().hide();
	}

	var conimm = mon.conditionImmune;
	if (conimm && conimm.length > 0) {
		$("td span#conimm").parent().show();
		$("td span#conimm").html(conimm);
	} else {
		$("td span#conimm").parent().hide();
	}

	var senses = mon.senses;
	if (senses && senses.length > 0) {
		$("td span#senses").html(senses+", ");
	} else {
		$("td span#senses").html("");
	}

	var passive = mon.passive;
	if (passive && passive.length > 0) {
		$("td span#pp").html(passive)
	}

	var languages = mon.languages;
	if (languages && languages.length > 0) {
		$("td span#languages").html(languages);
	} else {
		$("td span#languages").html("-");
	}

	var cr = mon.cr;
	$("td span#cr").html(cr);
	$("td span#xp").html(parsecr(cr));

	var traits = mon.trait;
	$("tr.trait").remove();

	if (traits) for (var i = traits.length-1; i >= 0; i--) {
		var traitname = traits[i].name;

		var traittext = traits[i].text;
		var traittexthtml = "";
		var renderedcount = 0;
		for (var n = 0; n < traittext.length; n++) {
			if (!traittext[n]) continue;

			renderedcount++;
			var firstsecond = ""
			if (renderedcount === 1) firstsecond = "first ";
			if (renderedcount === 2) firstsecond = "second ";

			var spells = "";
			if (traitname.indexOf("Spellcasting") !== -1 && traittext[n].indexOf(": ") !== -1) spells = "spells";
			if (traitname.indexOf("Variant") !== -1 && traitname.indexOf("Coven") !== -1 && traittext[n].indexOf(": ") !== -1) spells = "spells";

			traittexthtml = traittexthtml + "<p class='"+firstsecond+spells+"'>"+traittext[n].replace(/\u2022\s?(?=C|\d|At\swill)/g,"");+"</p>";
		}

		$("tr#traits").after("<tr class='trait'><td colspan='6' class='trait"+i+"'><span class='name'>"+traitname+".</span> "+traittexthtml+"</td></tr>");

		// parse spells, make hyperlinks
		$("tr.trait").children("td").children("p.spells").each(function() {
			var spellslist = $(this).html();
			if (spellslist[0] === "*") return;
			spellslist = spellslist.split(": ")[1].split(/\, (?!\+|\dd|appears|inside gems)/g);
			for (var i = 0; i < spellslist.length; i++) {
				spellslist[i] = "<a href='spells.html#"+encodeURIComponent(spellslist[i].replace(/(\*)| \(([^\)]+)\)/g,"")).toLowerCase().replace("'","%27")+"' target='_blank'>"+spellslist[i]+"</a>";
				if (i !== spellslist.length-1) spellslist[i] = spellslist[i]+", ";
			}

			$(this).html($(this).html().split(": ")[0]+": "+spellslist.join(""))
		});
	}

	var actions = mon.action;
	$("tr.action").remove();

	if (actions && actions.length) for (var i = actions.length-1; i >= 0; i--) {
		var actionname = actions[i].name;

		var actiontext = actions[i].text;
		var actiontexthtml = "";
		var renderedcount = 0;
		for (var n = 0; n < actiontext.length; n++) {
			if (!actiontext[n]) continue;

			renderedcount++;
			var firstsecond = ""
			if (renderedcount === 1) firstsecond = "first ";
			if (renderedcount === 2) firstsecond = "second ";

			actiontexthtml = actiontexthtml + "<p class='"+firstsecond+"'>"+actiontext[n]+"</p>";
		}

		$("tr#actions").after("<tr class='action'><td colspan='6' class='action"+i+"'><span class='name'>"+actionname+".</span> "+actiontexthtml+"</td></tr>");
	}

	var reactions = mon.reaction;
	$("tr#reactions").hide();
	$("tr.reaction").remove();

	if (reactions && reactions.length) {

		$("tr#reactions").show();

		if (!reactions.length) {
			var reactionname = reactions.name;

			var reactiontext = reactions.text;
			var reactiontexthtml = "";
			var renderedcount = 0
			for (var n = 0; n < reactiontext.length; n++) {
				if (!reactiontext[n]) continue;

				renderedcount++;
				var firstsecond = ""
				if (renderedcount === 1) firstsecond = "first ";
				if (renderedcount === 2) firstsecond = "second ";

				reactiontexthtml = reactiontexthtml + "<p class='"+firstsecond+"'>"+reactiontext[n]+"</p>";
			}

			$("tr#reactions").after("<tr class='reaction'><td colspan='6' class='reaction"+i+"'><span class='name'>"+reactionname+".</span> "+reactiontexthtml+"</td></tr>");
		}

		if (reactions.length) for (var i = reactions.length-1; i >= 0; i--) {
			var reactionname = reactions[i].name;

			var reactiontext = reactions[i].text;
			var reactiontexthtml = "<span>"+reactiontext+"</span>";
			for (var n = 1; n < reactiontext.length; n++) {
				if (!reactiontext[n]) continue;
				reactiontexthtml = reactiontexthtml + "<p>"+reactiontext[n]+"</p>";
			}

			$("tr#reactions").after("<tr class='reaction'><td colspan='6' class='reaction"+i+"'><span class='name'>"+reactionname+".</span> "+reactiontexthtml+"</td></tr>");
		}
	}


	var legendaries = mon.legendary;
	$("tr.legendary").remove();
	$("tr#legendaries").hide();
	if (legendaries && legendaries.length) {
		$("tr#legendaries").show();

		var legendarydescription = "<span>"+name+" can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature's turn. "+name+" regains spent legendary actions at the start of his turn."

		for (var i = legendaries.length-1; i >= 0; i--) {
			var legendaryname = "";
			var legendarytext = legendaries[i].text;
			var legendarytexthtml = "";

			if (legendaries[i].name) {
				legendaryname = legendaries[i].name+".";
			}


			var renderedcount = 0
			for (var n = 0; n < legendarytext.length; n++) {
				if (!legendarytext[n]) continue;

				renderedcount++;
				var firstsecond = ""
				if (renderedcount === 1) firstsecond = "first ";
				if (renderedcount === 2) firstsecond = "second ";

				legendarytexthtml = legendarytexthtml + "<p class='"+firstsecond+"'>"+legendarytext[n]+"</p>";
			}

			$("tr#legendaries").after("<tr class='legendary'><td colspan='6' class='legendary"+i+"'><span class='name'>"+legendaryname+"</span> "+legendarytexthtml+"</td></tr>");
		}

		if ($("tr.legendary").length && !$("tr.legendary span.name:empty").length && !$("tr.legendary span.name:contains(Legendary Actions)").length) {
			$("tr#legendaries").after("<tr class='legendary'><td colspan='6' class='legendary"+i+"'><span class='name'></span> <span>"+name+" can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature's turn. "+name+" regains spent legendary actions at the start of his turn.</span></td></tr>");

		}


	}

	// add click links for rollables
	$("#stats #abilityscores td").each(function() {
		$(this).wrapInner("<span class='roller' data-roll='1d20"+$(this).children(".mod").html()+"'></span>");
	});

	$("#skills,#saves").each(function() {
		$(this).html($(this).html().replace(/\+\d+/g, "<span class='roller' data-roll='1d20$&'>$&</span>"))
	});

	// inline rollers
	$("#stats p, #stats span#hp").each(function() {
		$(this).html($(this).html().replace(/\d+d\d+(\s?(\-|\+)\s?\d+\s?)?/g, "<span class='roller' data-roll='$&'>$&</span>"));

		$(this).html($(this).html().replace(/(\-|\+)\d+(?= to hit)/g, "<span class='roller' data-roll='1d20$&'>$&</span>"))

	});

	$(".spells span.roller").contents().unwrap();
	$("#stats span.roller").click(function() {
		var roll =$(this).attr("data-roll").replace(/\s+/g, "");
		var rollresult =  droll.roll(roll);
		var name = $("#name").clone().children().remove().end().text();
		$("div#output").prepend("<span>"+name + ": <em>"+roll+"</em> rolled for <strong>"+rollresult.total+"</strong> (<em>"+rollresult.rolls.join(", ")+"</em>)<br></span>").show();
		$("div#output span:eq(5)").remove();
	})

};
